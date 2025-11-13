from django.shortcuts import render
from django.http import JsonResponse, FileResponse
from django.views.decorators.csrf import csrf_exempt
from django.core.mail import send_mail
from django.conf import settings
import requests
import json
import base64
from datetime import datetime
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
import io
import os

# M-Pesa Daraja API Configuration
# For testing, use Safaricom Daraja sandbox
MPESA_CONSUMER_KEY = 'your_consumer_key_here'  # Get from Safaricom
MPESA_CONSUMER_SECRET = 'your_consumer_secret_here'  # Get from Safaricom
MPESA_SHORTCODE = '174379'  # Test credentials - change for production
MPESA_PASSKEY = 'your_passkey_here'  # Get from Safaricom
MPESA_CALLBACK_URL = 'https://yourdomain.com/mpesa-callback/'  # Update with your domain

# In-memory storage for demo (replace with database in production)
members_data = []
payment_status = {}


def index(request):
    return render(request, 'index.html')


def wie(request):
    return render(request, 'wie.html')


def news(request):
    return render(request, 'news.html')


def get_mpesa_access_token():
    """Get M-Pesa OAuth access token"""
    try:
        url = 'https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials'
        auth = (MPESA_CONSUMER_KEY, MPESA_CONSUMER_SECRET)
        response = requests.get(url, auth=auth, timeout=30)

        if response.status_code == 200:
            data = response.json()
            return data.get('access_token')
        else:
            print(f"MPesa token error: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"MPesa token exception: {e}")
        return None


@csrf_exempt
def register_member(request):
    """Register new ESA member"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)

            # Validate required fields
            required_fields = ['fullName', 'admissionNumber', 'department',
                               'admissionYear', 'graduationYear', 'email',
                               'phone', 'mpesaNumber']

            for field in required_fields:
                if field not in data or not data[field]:
                    return JsonResponse({
                        'success': False,
                        'message': f'Missing required field: {field}'
                    })

            # Generate batch number
            member_count = len(members_data) + 1
            batch_number = f"ESA-{datetime.now().strftime('%Y')}-{member_count:04d}"

            # Create member object
            member = {
                'id': member_count,
                'full_name': data['fullName'],
                'admission_number': data['admissionNumber'],
                'department': data['department'],
                'admission_year': int(data['admissionYear']),
                'graduation_year': int(data['graduationYear']),
                'email': data['email'],
                'phone': data['phone'],
                'mpesa_number': data['mpesaNumber'],
                'batch_number': batch_number,
                'membership_date': datetime.now().isoformat(),
                'payment_status': False,
                'transaction_id': None
            }

            # Store member data
            members_data.append(member)
            payment_status[member_count] = False

            return JsonResponse({
                'success': True,
                'member_id': member_count,
                'batch_number': batch_number,
                'message': 'Member registered successfully'
            })

        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'message': 'Invalid JSON data'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Registration error: {str(e)}'
            })

    return JsonResponse({'success': False, 'message': 'Only POST method allowed'})


@csrf_exempt
def initiate_mpesa_payment(request):
    """Initiate M-Pesa STK Push payment"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            phone = data.get('phone')
            amount = data.get('amount', 1)  # 1 KSh for testing

            if not phone:
                return JsonResponse({
                    'success': False,
                    'message': 'Phone number is required'
                })

            # Format phone number for M-Pesa
            if phone.startswith('0'):
                phone = '254' + phone[1:]
            elif phone.startswith('+254'):
                phone = phone[1:]
            elif not phone.startswith('254'):
                phone = '254' + phone

            # Get access token
            access_token = get_mpesa_access_token()
            if not access_token:
                return JsonResponse({
                    'success': False,
                    'message': 'Failed to get M-Pesa access token'
                })

            # Prepare STK Push request
            url = 'https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest'

            # Generate timestamp and password
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            password = base64.b64encode(
                f"{MPESA_SHORTCODE}{MPESA_PASSKEY}{timestamp}".encode()
            ).decode()

            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json'
            }

            payload = {
                "BusinessShortCode": MPESA_SHORTCODE,
                "Password": password,
                "Timestamp": timestamp,
                "TransactionType": "CustomerPayBillOnline",
                "Amount": amount,
                "PartyA": phone,
                "PartyB": MPESA_SHORTCODE,
                "PhoneNumber": phone,
                "CallBackURL": MPESA_CALLBACK_URL,
                "AccountReference": "ESA-01521258238000",  # Updated with actual account number
                "TransactionDesc": "ESA UoE Membership Fee - National Bank"
            }

            # Send STK Push request
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            response_data = response.json()

            if response_data.get('ResponseCode') == '0':
                return JsonResponse({
                    'success': True,
                    'checkout_request_id': response_data.get('CheckoutRequestID'),
                    'message': 'Payment request sent to your phone. Please check your M-Pesa menu and enter your PIN to complete the payment.'
                })
            else:
                error_message = response_data.get('ResponseDescription', 'Payment initiation failed')
                return JsonResponse({
                    'success': False,
                    'message': error_message
                })

        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Payment error: {str(e)}'
            })

    return JsonResponse({'success': False, 'message': 'Only POST method allowed'})


@csrf_exempt
def mpesa_callback(request):
    """Handle M-Pesa payment callback"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            print("MPesa Callback Received:", json.dumps(data, indent=2))

            # Extract callback data
            callback_data = data.get('Body', {}).get('stkCallback', {})
            result_code = callback_data.get('ResultCode')
            checkout_request_id = callback_data.get('CheckoutRequestID')

            if result_code == 0:
                # Payment successful
                print(f"Payment successful for {checkout_request_id}")

                # Extract transaction details
                callback_metadata = callback_data.get('CallbackMetadata', {}).get('Item', [])
                transaction_data = {}

                for item in callback_metadata:
                    transaction_data[item.get('Name')] = item.get('Value')

                # Update payment status (in production, update database)
                print(f"Transaction details: {transaction_data}")

                return JsonResponse({'status': 'success'})
            else:
                error_message = callback_data.get('ResultDesc', 'Payment failed')
                print(f"Payment failed: {error_message}")
                return JsonResponse({'status': 'failed', 'message': error_message})

        except Exception as e:
            print(f"Callback error: {e}")
            return JsonResponse({'status': 'error', 'message': str(e)})

    return JsonResponse({'status': 'error', 'message': 'Only POST method allowed'})


@csrf_exempt
def update_payment_status(request):
    """Update payment status for a member"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            member_id = data.get('member_id')

            if member_id and member_id in payment_status:
                payment_status[member_id] = True

                # Find member and update payment status
                for member in members_data:
                    if member['id'] == member_id:
                        member['payment_status'] = True
                        member['transaction_id'] = f"MPESA_{datetime.now().strftime('%Y%m%d%H%M%S')}"

                        # Send confirmation email
                        send_confirmation_email(member)
                        break

                return JsonResponse({'success': True, 'message': 'Payment status updated'})
            else:
                return JsonResponse({'success': False, 'message': 'Member not found'})

        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})

    return JsonResponse({'success': False, 'message': 'Only POST method allowed'})


@csrf_exempt
def send_confirmation_email_api(request):
    """API endpoint to send confirmation email"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            member_id = data.get('member_id')

            # Find member
            member = None
            for m in members_data:
                if m['id'] == member_id:
                    member = m
                    break

            if member:
                success = send_confirmation_email(member)
                if success:
                    return JsonResponse({'success': True, 'message': 'Email sent successfully'})
                else:
                    return JsonResponse({'success': False, 'message': 'Failed to send email'})
            else:
                return JsonResponse({'success': False, 'message': 'Member not found'})

        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})

    return JsonResponse({'success': False, 'message': 'Only POST method allowed'})


def send_confirmation_email(member):
    """Send membership confirmation email"""
    try:
        subject = '🎉 Welcome to Engineering Students Association - ESA UoE'

        message = f"""
        Dear {member['full_name']},

        Warmest congratulations and welcome to the Engineering Students' Association (ESA) at the University of Eldoret!

        We are thrilled to inform you that your membership has been successfully processed and confirmed. 

        YOUR MEMBERSHIP DETAILS:
        ───────────────────────
        • Membership Number: {member['batch_number']}
        • Full Name: {member['full_name']}
        • Admission Number: {member['admission_number']}
        • Department: {member['department']}
        • Membership Date: {datetime.now().strftime('%B %d, %Y')}
        • Status: ✅ ACTIVE MEMBER

        PAYMENT DETAILS:
        • Amount: KSh 500
        • Bank: National Bank of Kenya - Eldoret Branch
        • Account: 01521258238000
        • Transaction ID: {member.get('transaction_id', 'Pending')}

        As a registered member of ESA, you now have access to:
        🔧 Engineering workshops and technical seminars
        🤝 Industry networking events and career fairs
        🏆 Technical competitions and innovation challenges
        📚 Career development and mentorship programs
        👥 Collaborative projects and team activities
        🎨 ESA merchandise and exclusive resources

        UPCOMING ORIENTATION:
        We will be hosting a new members orientation session next week. Keep an eye on your email for the date, time, and venue details.

        STAY CONNECTED:
        • Check your email regularly for ESA updates
        • Join our WhatsApp group for real-time communication
        • Follow us on social media for the latest news

        We believe in your potential to become a future engineering leader, and we're excited to support your journey every step of the way.

        Should you have any questions or need assistance, please don't hesitate to contact us at esauoe@uoeld.ac.ke.

        Once again, welcome to the ESA family!

        Best regards,

        ESA Executive Committee 2025
        Engineering Students' Association
        University of Eldoret
        Email: esauoe@uoeld.ac.ke

        "Building Future Engineers, Shaping Tomorrow's World"
        """

        # For demo purposes, we'll print the email instead of sending
        print(f"\n{'=' * 60}")
        print("MEMBERSHIP CONFIRMATION EMAIL")
        print(f"{'=' * 60}")
        print(f"To: {member['email']}")
        print(f"Subject: {subject}")
        print(f"{'-' * 60}")
        print(message)
        print(f"{'=' * 60}\n")

        # Uncomment below to send actual email when configured
        """
        send_mail(
            subject,
            message,
            'esauoe@uoeld.ac.ke',
            [member['email']],
            fail_silently=False,
        )
        """

        return True

    except Exception as e:
        print(f"Email error: {e}")
        return False


def generate_membership_pdf(request, member_id):
    """Generate and download membership card PDF"""
    try:
        # Find member
        member = None
        for m in members_data:
            if m['id'] == int(member_id):
                member = m
                break

        if not member:
            return JsonResponse({'success': False, 'message': 'Member not found'})

        # Create PDF in memory
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.5 * inch, bottomMargin=0.5 * inch)

        # Create styles
        styles = getSampleStyleSheet()

        # Custom styles
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#3E2723'),
            alignment=TA_CENTER,
            spaceAfter=30
        )

        header_style = ParagraphStyle(
            'CustomHeader',
            parent=styles['Heading2'],
            fontSize=16,
            textColor=colors.HexColor('#CD7F32'),
            alignment=TA_CENTER,
            spaceAfter=20
        )

        normal_style = ParagraphStyle(
            'CustomNormal',
            parent=styles['Normal'],
            fontSize=12,
            textColor=colors.HexColor('#2C3E50'),
            alignment=TA_LEFT
        )

        # Build story (content)
        story = []

        # Title
        story.append(Paragraph("ENGINEERING STUDENTS' ASSOCIATION", title_style))
        story.append(Paragraph("University of Eldoret", header_style))
        story.append(Spacer(1, 20))

        # Membership Card
        story.append(Paragraph("OFFICIAL MEMBERSHIP CARD", header_style))
        story.append(Spacer(1, 30))

        # Member details in a table
        member_data = [
            ['Full Name:', member['full_name']],
            ['Admission Number:', member['admission_number']],
            ['Department:', member['department']],
            ['Batch Number:', member['batch_number']],
            ['Membership Date:', datetime.now().strftime('%B %d, %Y')],
            ['Admission Year:', str(member['admission_year'])],
            ['Graduation Year:', str(member['graduation_year'])],
            ['Email:', member['email']],
            ['Phone:', member['phone']]
        ]

        member_table = Table(member_data, colWidths=[2 * inch, 4 * inch])
        member_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F5F5F5')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#3E2723')),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#E0E0E0'))
        ]))

        story.append(member_table)
        story.append(Spacer(1, 40))

        # === ADD PAYMENT ACCOUNT INFO HERE ===
        payment_info = [
            ['Payment Account:', 'National Bank of Kenya - Eldoret Branch'],
            ['Account Name:', 'ENGINEERING STUDENTS\' ASSOCIATION'],
            ['Account Number:', '01521258238000'],
            ['Branch Code:', '040']
        ]

        payment_table = Table(payment_info, colWidths=[2 * inch, 4 * inch])
        payment_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#E8F5E8')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#2C3E50')),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#C8E6C9'))
        ]))

        story.append(Paragraph("Payment Details", header_style))
        story.append(payment_table)
        story.append(Spacer(1, 30))
        # === END PAYMENT ACCOUNT INFO ===

        # Official Stamp
        stamp_style = ParagraphStyle(
            'StampStyle',
            parent=styles['Normal'],
            fontSize=18,
            textColor=colors.HexColor('#B71C1C'),
            alignment=TA_CENTER,
            borderWidth=2,
            borderColor=colors.HexColor('#B71C1C'),
            borderPadding=10,
            backColor=colors.HexColor('#FFEBEE')
        )

        story.append(Paragraph("OFFICIALLY CERTIFIED", stamp_style))
        story.append(Spacer(1, 10))
        story.append(Paragraph("ESA UOE 2025", stamp_style))
        story.append(Spacer(1, 30))

        # Terms and conditions
        terms_text = """
        <b>Terms & Conditions:</b><br/>
        • This membership card is the property of Engineering Students' Association<br/>
        • Valid for the academic year 2025<br/>
        • Non-transferable<br/>
        • Must be presented at all ESA events<br/>
        • Subject to ESA constitution and regulations
        """

        story.append(Paragraph(terms_text, normal_style))
        story.append(Spacer(1, 20))

        # Signature area
        signature_text = """
        <br/><br/><br/>
        _________________________<br/>
        <b>ESA President Signature</b><br/>
        Engineering Students' Association<br/>
        University of Eldoret
        """

        story.append(Paragraph(signature_text, normal_style))

        # Build PDF
        doc.build(story)

        # Prepare response
        buffer.seek(0)
        filename = f"esa_membership_{member['batch_number']}.pdf"

        response = FileResponse(buffer, as_attachment=True, filename=filename)
        response['Content-Type'] = 'application/pdf'

        return response

    except Exception as e:
        return JsonResponse({'success': False, 'message': f'PDF generation error: {str(e)}'})


def get_members_data(request):
    """API endpoint to get all members data (for admin)"""
    if request.method == 'GET':
        return JsonResponse({
            'success': True,
            'members': members_data,
            'total_members': len(members_data),
            'paid_members': len([m for m in members_data if m.get('payment_status', False)])
        })

    return JsonResponse({'success': False, 'message': 'Only GET method allowed'})


# For testing payment simulation
@csrf_exempt
def simulate_payment_success(request):
    """Simulate successful payment for testing"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            member_id = data.get('member_id')

            if member_id:
                # Update payment status
                for member in members_data:
                    if member['id'] == member_id:
                        member['payment_status'] = True
                        member['transaction_id'] = f"SIM_{datetime.now().strftime('%Y%m%d%H%M%S')}"
                        break

                payment_status[member_id] = True

                return JsonResponse({
                    'success': True,
                    'message': 'Payment simulated successfully'
                })
            else:
                return JsonResponse({
                    'success': False,
                    'message': 'Member ID required'
                })

        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': str(e)
            })

    return JsonResponse({'success': False, 'message': 'Only POST method allowed'})