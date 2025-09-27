# Review Buddy - A Code Review Telegram Bot

This is a Telegram bot designed to help with code reviews in small or personal projects.

## Features

*   **Review Reminders:** The bot can check for open pull requests and send reminders.
*   **Random Reviews:** The `/random_review` command selects a random file from a random open PR for you to review.
*   **Linter Integration:** The bot can be integrated with linters like ESLint and Pylint to perform basic static analysis.
*   **PR Tracking:** Proactively tracks repositories and notifies you of new pull requests.

## Tech Stack

*   **Language:** Python
*   **Framework:** python-telegram-bot
*   **Database:** Firebase Firestore

## Libraries Used

*   `python-telegram-bot[job-queue]`: The core framework for interacting with the Telegram Bot API. The `[job-queue]` extra is used for running background tasks.
*   `pygithub`: A Python library to access the GitHub API, used for fetching pull requests and repository data.
*   `firebase-admin`: The Admin SDK for Firebase, used to connect to and manage the Firestore database.
*   `pygments`: A generic syntax highlighter used to generate images of code files.
*   `python-dotenv`: A library for managing environment variables, used for loading the bot token.

## Getting Started

1.  **Clone the repository:**
    ```bash
    git clone <repository-url>
    ```

2.  **Install dependencies:**
    ```bash
    uv add python-telegram-bot[job-queue] pygithub firebase-admin pygments python-dotenv
    ```

3.  **Set up your Bot Token:**
    *   Create a `.env` file in the root of the project.
    *   Add your Telegram bot token to it:
      ```
      BOT_TOKEN='YOUR_BOT_TOKEN'
      ```

4.  **Set up Firebase:**
    *   Go to the [Firebase Console](https://console.firebase.google.com/) and create a new project.
    *   Go to **Project settings > Service accounts**.
    *   Click **"Generate new private key"** and download the credentials file.
    *   Rename the downloaded file to `firebase_credentials.json` and place it in the project root.
    *   Go to the **Firestore Database** section in the Firebase console and create a database. Choose **Native mode** and select your preferred location.

5.  **Run the bot:**
    ```bash
    uv run main.py
    ```

## How it Works

The bot connects to Telegram and GitHub APIs and uses a Firebase Firestore database to store user data, including GitHub tokens and tracked repositories. A background job periodically checks for new pull requests and sends notifications to users who have enabled tracking.
