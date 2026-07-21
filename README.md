# PhishGuard

PhishGuard is a phishing detection project that combines classical machine learning, quantum-inspired models, a Flask web app, and a browser extension to score URLs in real time.

## What It Does

- Scans a URL against 9 phishing detection models.
- Provides a web dashboard for single URL analysis, batch scans, analytics, and a quantum circuit visualizer.
- Ships with a browser extension that checks the current tab and warns users before they continue to suspicious pages.
- Stores scan history in a local SQLite database.

## Features

- Flask-based web app with login, scan history, dashboard, batch upload, and visualizer pages.
- 6 classical models and 3 quantum models combined through majority voting.
- Local browser extension for real-time URL protection.
- SQLite-backed scan history and per-user analytics.

## Setup

1. Install Python dependencies:

	```bash
	cd phishing_site_root
	pip install -r requirements.txt
	```

2. Generate the processed dataset if it does not already exist:

	- Open `phishing_site_root/models/preprocessing/data_preprocessing.ipynb`
	- Run the notebook to create `phishing_site_root/models/preprocessing/processed_data.csv`

3. Create environment variables:

	```bash
	cd phishing_site_root/webapp
	copy .env.example .env
	```

	Set `SECRET_KEY` before deploying, and optionally configure OAuth values if you want to experiment with them.

## Run the App

Start the Flask app from the `webapp` directory:

```bash
cd phishing_site_root/webapp
python app.py
```

The app runs on `http://127.0.0.1:5000`.

## Usage

- Open the landing page at `/`.
- Register or sign in at `/auth/register` or `/auth/login`.
- Use `/analyser` to scan a single URL.
- Use `/batch` to upload a CSV of URLs.
- Use `/dashboard` to review scan history and analytics.
- Use `/visualizer` to inspect the quantum circuit encoding.

To use the browser extension, load the unpacked extension from `phishing_site_root/browser_extension` and keep the Flask app running locally.

## Folder Structure

```text
phishing_site_root/
├── browser_extension/   # Chrome/Firefox extension
├── models/              # Preprocessing, classical, and quantum model assets
├── testing/             # Sample test URLs
└── webapp/              # Flask app, API, auth, database, templates, and static files
```

## Notes

- The project is designed to run locally.
- The web app initializes the database and loads the model pipeline on startup.
- Batch scanning skips quantum models for speed.