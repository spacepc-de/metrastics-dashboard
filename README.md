# Metrastics - Meshtastic Dashboard

Watch it live: https://metrastics.com/

A Django-based web application to monitor and visualize data from a Meshtastic network via MQTT.

## Table of Contents

- [Features](#features)
- [Project Goal](#project-goal)
- [Requirements](#requirements)
- [Setup and Installation](#setup-and-installation)
  - [1. Clone the Repository](#1-clone-the-repository)
  - [2. Create and Activate a Virtual Environment](#2-create-and-activate-a-virtual-environment)
  - [3. Install Dependencies](#3-install-dependencies)
  - [4. Configure Settings](#4-configure-settings)
  - [5. Apply Database Migrations](#5-apply-database-migrations)
  - [6. Create a Superuser](#6-create-a-superuser)
  - [7. Collect Static Files](#7-collect-static-files)
- [Running the Application](#running-the-application)
  - [1. Start the MQTT Listener](#1-start-the-mqtt-listener)
  - [2. Run the Django Development Server](#2-run-the-django-development-server)
- [Project Structure](#project-structure)
- [Contributing](#contributing)
- [License](#license)

## Features

* **MQTT Listener:** Subscribes to Meshtastic MQTT topics to receive real-time data about nodes, positions, messages, etc.
* **Dashboard Overview:** A central place to view key statistics and information from your Meshtastic network.
* **Node List:** Displays a list of all detected nodes in the network.
* **Node Detail View:** Shows detailed information for each specific node, including its hardware, software version, and last heard time.
* **Message List:** Lists text messages exchanged over the mesh.
* **Map View:** Visualizes node positions on a map (requires appropriate GPS data from nodes).
* **Django Admin Interface:** Provides a backend interface to manage raw data (nodes, messages, packets).
* **Styled with Bootstrap 5:** Clean and responsive user interface.

## Project Goal

The primary goal of this project is to provide a user-friendly web interface for monitoring a Meshtastic mesh network. It leverages MQTT to gather data and Django to present it in a structured and accessible manner. This can be useful for community mesh operators, enthusiasts, or anyone wanting to get a better overview of their Meshtastic network activity.

## Requirements

The project relies on the following major dependencies (see `requirements.txt` for a full list):

* Python 3.8+
* Django 5.0.6
* Paho-MQTT 2.1.0 (for connecting to MQTT brokers)
* django-bootstrap5 23.4 (for UI styling)

You will also need access to an MQTT broker that is relaying Meshtastic data (e.g., a local broker, or a public one if your nodes are configured to use it).

## Setup and Installation

Follow these steps to get the project running locally:

### 1. Clone the Repository

```bash
git clone <your-repository-url>
cd meshtastic_dashboard
2. Create and Activate a Virtual Environment

It's highly recommended to use a virtual environment:

Bash
python -m venv venv
# On Windows
venv\Scripts\activate
# On macOS/Linux
source venv/bin/activate
3. Install Dependencies

Install all required packages using pip:

Bash
pip install -r requirements.txt
4. Configure Settings

The main Django settings are in meshtastic_dashboard/settings.py. You may need to adjust the following:

SECRET_KEY: Ensure this is unique and kept secret if deploying.

DEBUG: Set to False for production.

ALLOWED_HOSTS: Add your domain/IP if deploying.

Database: By default, it uses SQLite (db.sqlite3). You can configure it to use PostgreSQL, MySQL, or other databases supported by Django.

Python
# meshtastic_dashboard/settings.py
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}
 MQTT Broker Configuration (for listen_mqtt command):
The MQTT listener script (mqtt_listener/management/commands/listen_mqtt.py) will need to know your MQTT broker's address, port, and potentially credentials. You might need to modify this script or, ideally, use environment variables or Django settings to configure:

MQTT_BROKER_HOST
MQTT_BROKER_PORT
MQTT_TOPIC (e.g., msh/#)
MQTT_USERNAME (if applicable)
MQTT_PASSWORD (if applicable)
Currently, these are hardcoded in the listen_mqtt.py command. Consider refactoring to pull from settings.py or environment variables for better security and flexibility.
Example (modify listen_mqtt.py or add to settings.py and adapt the command):

Python
# In settings.py (example)
MQTT_BROKER_HOST = 'your_mqtt_broker_ip_or_hostname'
MQTT_BROKER_PORT = 1883  # Or your MQTT port
MQTT_USERNAME = None  # Or your MQTT username
MQTT_PASSWORD = None  # Or your MQTT password
MQTT_TOPIC_PREFIX = "msh" # Your Meshtastic MQTT topic prefix
5. Apply Database Migrations

Create the database schema by running:

Bash
python manage.py migrate
6. Create a Superuser

 To access the Django admin interface, create a superuser:

Bash
python manage.py createsuperuser
Follow the prompts to set a username, email, and password.

7. Collect Static Files

For development, Django's development server often handles static files. For production, or if you encounter issues:

Bash
python manage.py collectstatic
Running the Application
You need to run two main processes: the MQTT listener and the Django web server.

1. Start the MQTT Listener

This command connects to the MQTT broker, subscribes to Meshtastic topics, and stores incoming data into the database.
Open a new terminal window/tab, activate the virtual environment, and run:

Bash
python manage.py listen_mqtt
Ensure your MQTT broker details are correctly configured in the script or Django settings as mentioned in the configuration step.

2. Run the Django Development Server

In another terminal window/tab, activate the virtual environment, and start the web server:

Bash
python manage.py runserver
By default, the application will be available at http://127.0.0.1:8000/.
You can access the admin interface at http://127.0.0.1:8000/admin/.
The main dashboard views can be accessed via /, /nodes/, /messages/, /map/ (or check mqtt_listener/urls.py for exact paths).

Project Structure
meshtastic_dashboard/
├── manage.py                   # Django's command-line utility
├── meshtastic_dashboard/       # Django project directory
│   ├── __init__.py
│   ├── asgi.py                 # ASGI config for deployment
│   ├── settings.py             # Django settings
│   ├── urls.py                 # Project-level URL routing
│   └── wsgi.py                 # WSGI config for deployment
├── mqtt_listener/              # Django app for MQTT listening and dashboard views
│   ├── __init__.py
│   ├── admin.py                # Django admin configurations for models
│   ├── apps.py                 # App configuration
│   ├── management/             # Custom Django management commands
│   │   └── commands/
│   │       └── listen_mqtt.py  # The MQTT listener script
│   ├── migrations/             # Database migrations
│   ├── models.py               # Database models (Nodes, Messages, Packets)
│   ├── static/                 # Static files specific to this app (CSS, JS)
│   │   └── mqtt_listener/
│   │       └── style.css
│   ├── templates/              # HTML templates
│   │   └── mqtt_listener/
│   │       ├── base.html
│   │       ├── dashboard_overview.html
│   │       ├── map_view.html
│   │       ├── message_list.html
│   │       ├── node_detail.html
│   │       └── node_list.html
│   │       └── ... (other templates)
│   ├── tests.py                # App-specific tests
│   ├── urls.py                 # App-level URL routing
│   └── views.py                # Views (request handlers)
├── requirements.txt            # Python package dependencies
├── staticfiles/                # Collected static files (after running collectstatic)
└── db.sqlite3                  # Default SQLite database file
Contributing
Contributions are welcome! If you'd like to contribute, please follow these general steps:

License
This project is licensed under the MIT License. See the LICENSE file for more details.

Copyright (c) 2024 Jonathan Stöcklmayer

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
