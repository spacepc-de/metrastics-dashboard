# AGENTS Anweisungen

Diese Datei definiert Richtlinien für die Arbeit an diesem Repository. Ihr Geltungsbereich umfasst das gesamte Projekt.

## Vue Single-Page-Application und Routing
- Das Frontend wird als Vue-3-Single-Page-Application entwickelt.
- Verwende **vue-router** im History-Modus für die Navigation zwischen Komponenten.
- Neue Routen werden in `frontend/src/router/index.js` registriert und verweisen auf eigene Komponenten in `frontend/src/views`.

## Styling mit Tailwind CSS
- Das Styling erfolgt mit **Tailwind CSS**.
- Die Konfiguration liegt in `frontend/tailwind.config.js`.
- Globale Styles liegen in `frontend/src/index.css`.

## Trennung von Frontend und Backend
- Der Quellcode ist strikt getrennt: Vue-Code im Verzeichnis `frontend/`, das Django-Backend im Verzeichnis `metrastics_dashboard/`.
- Kommunikation erfolgt ausschließlich über HTTP-APIs (REST/GraphQL) oder WebSockets. Keine serverseitigen Templates für Vue-Seiten.
- Baue das Frontend mit `npm run build`; die erzeugten Dateien werden unter `backend/static/` bereitgestellt.

## Live-Daten in der Benutzeroberfläche
- Für Echtzeitaktualisierungen der GUI sind WebSockets oder Server-Sent Events zu verwenden.
- Implementiere einen zentralen Datenservice (`frontend/src/services/liveData.js`), der eingehende Nachrichten verarbeitet und als Reactive Source für Komponenten dient.
- Komponenten abonnieren diesen Service, um angezeigte Messwerte automatisch zu aktualisieren.

## Tests
- Führe vor jedem Commit `python manage.py test` aus und stelle sicher, dass alle Tests erfolgreich sind.
