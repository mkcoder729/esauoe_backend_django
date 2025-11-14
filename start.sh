#!/bin/bash
pip install Django==4.2.19 reportlab==4.0.4 requests==2.31.0 Pillow==9.5.0
python manage.py migrate
python manage.py runserver 0.0.0.0:$PORT