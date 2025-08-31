# Metrastics: Meshtastic Network Analyzer & Commander

Metrastics is a Django-based web application designed to listen to a Meshtastic network, store device and packet information, and provide a comprehensive dashboard for visualizing this data. It also includes a "Commander" feature for rule-based automated responses to messages and integration with OpenAI's ChatGPT.

## Features

* **Live Data Listening:** Connects to a Meshtastic device (via TCP/IP) to listen for live packet data, node updates, and connection status.
* **Data Persistence:** Stores all received information (nodes, packets, messages, positions, telemetry) in a database.
* **Dashboard Overview:**
    * Displays listener and local node status.
    * Shows average signal statistics (SNR/RSSI) over the last 12 hours.
    * Provides counters for total packets, nodes, and various packet types (messages, positions, telemetry, user info, traceroutes).
    * Includes an overview map of all nodes with known locations.
    * Lists recently active nodes with key information.
    * Features a live packet feed displaying recent network activity.
* **Nodes Page:**
    * Lists all discovered nodes with detailed information.
    * Search functionality for nodes (by name, ID, hardware model).
    * Pagination for easy navigation.
    * Modal view for detailed node information, including:
        * General details (ID, name, hardware, firmware, role).
        * Status (last heard, battery, signal, uptime).
        * Position data and a map of the node's last known location.
        * Detailed telemetry (device and environment metrics).
        * Raw JSON data (user info, module config, channel info).
* **Map Page:** Displays all nodes with valid location data on a Leaflet map.
* **Commander Module:**
    * Define rules to automatically respond to incoming Meshtastic messages.
    * Rules can be based on exact match, contains, startswith, or regex for the trigger phrase.
    * Use placeholders in response templates to include dynamic data from the sender, local node, or message.
    * Set cooldown periods for rules per node.
    * **ChatGPT Integration:** Interact with OpenAI's ChatGPT directly via Meshtastic. Send a message starting with a configurable trigger command (e.g., `!chat`) followed by your query.
* **Admin Interface:** Full Django admin interface for managing raw data models (Nodes, Packets, Messages, etc.) and Commander Rules.

## Technology Stack

* **Backend:** Django, Python
* **Meshtastic Interaction:** `meshtastic` Python library
* **Database:** SQLite (default), configurable via `DATABASE_URL` (e.g., PostgreSQL)
* **Frontend:** Vue 3, Tailwind CSS, Vite
* **Mapping:** Leaflet.js
* **Real-time Updates:** WebSockets
* **Environment Management:** `python-dotenv`
* **AI Integration:** `openai` Python library

## Project Structure

The project consists of a Vue frontend and multiple Django apps for the backend:

* `frontend`: Vue 3 single-page application built with Vite and Tailwind CSS.
* `metrastics_listener`: Contains models for all Meshtastic data (Node, Packet, Message, Position, Telemetry, etc.) and the management command (`listen_device`) responsible for connecting to the Meshtastic device, processing incoming data, and saving it to the database. It also handles the Flask-based API endpoint for sending messages and is configured to start automatically with the Django development server.
* `metrastics_dashboard`: Provides the views, templates, and API endpoints for the web-based user interface where users can view the collected data, node details, maps, and live feeds.
* `metrastics_commander`: Manages the rules for automated responses and the ChatGPT integration. It includes models for `CommanderRule` and views for managing these rules via the UI and an API.

## Setup and Installation

1.  **Clone the Repository:**
    ```bash
    git clone [https://github.com/spacepc-de/metrastics-dashboard.git](https://github.com/spacepc-de/metrastics-dashboard.git)
    cd metrastics-dashboard 
    ```

2.  **Create and Activate a Virtual Environment:**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```

3.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
   

4.  **Configure Environment Variables:**
    Create a `.env` file in the project root directory (same level as `manage.py`).
    Copy the contents from `.env.example` (if provided) or create it with the following content, adjusting values as needed:

    ```env
    # Django Settings
    SECRET_KEY=your_strong_secret_key_here  # Replace with a strong, unique key
    DEBUG=True  # Set to False for production
    ALLOWED_HOSTS=localhost,127.0.0.1 # Comma-separated list of allowed hosts

    # Database Settings (Default is SQLite)
    # DATABASE_URL=sqlite:///db.sqlite3
    # Example for PostgreSQL:
    # DATABASE_URL=postgres://user:password@host:port/dbname

    # Timezone and Language
    LANGUAGE_CODE=en-us
    TIME_ZONE=UTC # e.g., Europe/Berlin

    # Meshtastic Device Connection
    MESHTASTIC_DEVICE_HOST=localhost # Hostname or IP of the device running meshtastic-device (TCP interface)
    MESHTASTIC_DEVICE_PORT=4403      # Port for the Meshtastic TCP interface

    # Logging Levels (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    DJANGO_LOG_LEVEL=INFO
    LISTENER_LOG_LEVEL=INFO
    COMMANDER_LOG_LEVEL=INFO
    MESHTASTIC_LIB_LOG_LEVEL=INFO # Set to WARNING or ERROR to reduce Meshtastic library verbosity
    PUBSUB_LOG_LEVEL=WARNING
    OPENAI_LOG_LEVEL=INFO
    ROOT_LOG_LEVEL=INFO

    # OpenAI / ChatGPT Integration
    OPENAI_API_KEY="your_openai_api_key_here" # Replace with your actual OpenAI API key
    CHATGPT_TRIGGER_COMMAND="!chat"
    CHATGPT_SYSTEM_PROMPT="You are a helpful assistant on a Meshtastic network. Keep your answers concise due to message length limitations. Max 200byte Answer"

    ```
   
    **Important:** The `listen_device.py` script uses a hardcoded port `5555` for its internal Flask app that facilitates sending messages. Ensure this port is free or modify the script if needed.

5.  **Run Database Migrations:**
    ```bash
    python manage.py migrate
    ```
    This will create the necessary database tables based on the models in `metrastics_listener`, `metrastics_commander`, and other Django apps.

6.  **Create a Superuser (for Admin Access):**
    ```bash
    python manage.py createsuperuser
    ```
    Follow the prompts to create an administrator account.

7.  **Start the Django Development Server:**
    ```bash
    python manage.py runserver
    ```
    The Meshtastic listener (`listen_device` command) is configured to start automatically in a separate thread when the Django development server starts. You should see log messages indicating its startup in the console.
    By default, the web application will be accessible at `http://127.0.0.1:8000/`.

## Frontend Development

The Vue frontend lives in `frontend/`.

Install dependencies:

```bash
cd frontend
npm install
```

Run the development server:

```bash
npm run dev
```

Build production assets:

```bash
npm run build
```

The build outputs to `metrastics_dashboard/static/` to be served by Django.

## Run with Docker Compose

An easier way to start the project is via Docker Compose. This builds containers for the Django backend and the Vue development server.

1. Copy `.env.example` to `.env` and adjust values as needed.
2. Build and start the service:

    ```bash
    docker-compose up --build
    ```

   The backend API will be available at [http://localhost:8000](http://localhost:8000) and the frontend dev server at [http://localhost:5173](http://localhost:5173).

## Usage

* **Dashboard:** Access the main dashboard at `http://127.0.0.1:8000/dashboard/` (or the root `/` if configured as such).
* **Nodes List:** Navigate to `http://127.0.0.1:8000/dashboard/nodes/`.
* **Nodes Map:** Navigate to `http://127.0.0.1:8000/dashboard/map/`.
* **Commander Rules:** Access the Commander interface at `http://127.0.0.1:8000/commander/`.
    * View existing rules.
    * Edit basic properties of rules (name, trigger, response, cooldown, enabled status).
    * For adding new rules or more complex modifications, use the Django Admin interface.
* **Admin Interface:** Access at `http://127.0.0.1:8000/admin/` and log in with your superuser credentials. Here you can manage all data and Commander rules directly.

## Configuration Details

Key configurations are managed via the `.env` file:

* `SECRET_KEY`: A long, random string used for cryptographic signing. **Keep this secret in production.**
* `DEBUG`: Set to `False` in a production environment.
* `ALLOWED_HOSTS`: A list of hostnames/IPs that are allowed to access the application.
* `DATABASE_URL`: Specifies the database connection. Defaults to a local SQLite file (`db.sqlite3`).
* `TIME_ZONE`: Sets the timezone for the application.
* `MESHTASTIC_DEVICE_HOST` & `MESHTASTIC_DEVICE_PORT`: Define how to connect to your Meshtastic node's TCP interface.
* `OPENAI_API_KEY`: Your API key from OpenAI for ChatGPT integration.
* `CHATGPT_TRIGGER_COMMAND`: The command prefix to trigger ChatGPT interaction over Meshtastic.
* `CHATGPT_SYSTEM_PROMPT`: The system prompt used to instruct ChatGPT on its behavior.
* Various `*_LOG_LEVEL` variables: Control the verbosity of logging for different parts of the application.

## Contributing

Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

Please make sure to update tests as appropriate.

## License

MIT License

Copyright (c) 2025 Jonathan Stöcklmayer - Metrastics

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
