import os
import random
import asyncio
import telegram
from telegram.ext import (
    Application,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
    ContextTypes
)
from dotenv import load_dotenv
from github import Github, GithubException
from pygments import highlight
from pygments.lexers import get_lexer_by_name
from pygments.formatters import ImageFormatter
import firebase_admin
from firebase_admin import credentials, firestore

# --- Firebase Initialization ---
try:
    cred = credentials.Certificate("firebase_credentials.json")
    firebase_admin.initialize_app(cred)
    db = firestore.client()
except Exception as e:
    print(f"Failed to initialize Firebase: {e}")
    db = None

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')

# Conversation states
(ASK_TOKEN, ASK_REPO, UPDATE_TOKEN, UPDATE_REPO, 
 TRACK_REPO, UNTRACK_REPO) = range(6)

# --- Firestore Helper Functions ---
def get_user_data(user_id):
    if not db: return {}
    doc_ref = db.collection('users').document(str(user_id))
    doc = doc_ref.get()
    return doc.to_dict() if doc.exists else {}

def set_user_data(user_id, data):
    if not db: return
    db.collection('users').document(str(user_id)).set(data, merge=True)

# --- Command Handlers ---
async def start(update, context):
    if not db:
        await update.message.reply_text("Error: Firebase is not connected.")
        return ConversationHandler.END

    user_id = update.message.from_user.id
    user_data = get_user_data(user_id)

    if 'github_token' not in user_data:
        await update.message.reply_text(
            "Hello! I am your Code Review Buddy.\n\n"
            "Please provide your GitHub personal access token."
        )
        return ASK_TOKEN
    else:
        await update.message.reply_text(
            "Welcome back! You're all set. Use /help to see available commands."
        )
        return ConversationHandler.END

async def ask_repo_for_setup(update, context):
    context.user_data['github_token_temp'] = update.message.text
    await update.message.reply_text(
        "Great! Now, please enter your primary repository name (e.g., 'username/repository')."
    )
    return ASK_REPO

async def set_repo_and_finish_setup(update, context):
    user_id = update.message.from_user.id
    repo_name = update.message.text
    token = context.user_data.get('github_token_temp')

    if not token:
        await update.message.reply_text("Something went wrong. Please try /start again.")
        return ConversationHandler.END

    set_user_data(user_id, {'github_token': token, 'repo_name': repo_name, 'tracked_repos': {}})
    await update.message.reply_text(
        f"Primary repository set to {repo_name}. You can now use commands like /random_review and /track."
    )
    context.user_data.clear()
    return ConversationHandler.END

async def help_command(update, context):
    await update.message.reply_text(
        "Available commands:\n"
        "/start - Initialize the bot.\n"
        "/random_review - Get a random file from your primary repository.\n"
        "/track - Track a new repository for PR notifications.\n"
        "/untrack - Stop tracking a repository.\n"
        "/tracked - List all tracked repositories.\n"
        "/set_repo - Change your primary repository.\n"
        "/set_token - Update your GitHub token.\n"
        "/cancel - Cancel the current operation."
    )

async def random_review(update, context):
    if not db: return await update.message.reply_text("Error: Firebase is not connected.")
    user_id = update.message.from_user.id
    user_data = get_user_data(user_id)

    if 'github_token' not in user_data or 'repo_name' not in user_data:
        return await update.message.reply_text("Please set your token and primary repo using /start or /set_repo.")

    try:
        await update.message.reply_text(f"Searching for a random file in {user_data['repo_name']}...")
        g = Github(user_data['github_token'])
        repo = g.get_repo(user_data['repo_name'])
        pulls = [p for p in repo.get_pulls(state='open')]

        if not pulls:
            return await update.message.reply_text("No open pull requests found.")

        pull = random.choice(pulls)
        files = [f for f in pull.get_files()]

        if not files:
            return await update.message.reply_text("No files found in the chosen pull request.")
        
        file = random.choice(files)
        content = repo.get_contents(file.filename, ref=pull.head.ref).decoded_content.decode('utf-8')
        lexer = get_lexer_by_name(os.path.splitext(file.filename)[1][1:], stripall=True) if "." in file.filename else get_lexer_by_name('text')
        formatter = ImageFormatter(font_size=16, line_numbers=False, style='solarized-dark')
        
        await context.bot.send_photo(
            chat_id=update.effective_chat.id, 
            photo=highlight(content, lexer, formatter),
            caption=f"File: {file.filename}\nPR: {pull.title} (#{pull.number})"
        )
    except GithubException as e:
        await update.message.reply_text(f"GitHub Error: {e.data.get('message', 'Unknown')}")
    except Exception as e:
        await update.message.reply_text(f"An error occurred: {e}")

# --- PR Tracking ---
async def track_repo_start(update, context):
    await update.message.reply_text("Which repository do you want to track? (e.g., 'username/repository')")
    return TRACK_REPO

async def track_repo_finish(update, context):
    user_id = update.message.from_user.id
    repo_name = update.message.text
    user_data = get_user_data(user_id)

    try:
        g = Github(user_data.get('github_token'))
        repo = g.get_repo(repo_name)
        pulls = repo.get_pulls(state='all', sort='created', direction='desc')
        latest_pr_number = pulls[0].number if pulls.totalCount > 0 else 0

        tracked_repos = user_data.get('tracked_repos', {})
        tracked_repos[repo_name] = {'last_pr_number': latest_pr_number}
        set_user_data(user_id, {'tracked_repos': tracked_repos})
        
        await update.message.reply_text(f"Started tracking {repo_name}. I will notify you about new pull requests.")
    except Exception as e:
        await update.message.reply_text(f"Could not add repository. Error: {e}")
    return ConversationHandler.END

async def untrack_repo_start(update, context):
    await update.message.reply_text("Which repository do you want to stop tracking? (e.g., 'username/repository')")
    return UNTRACK_REPO

async def untrack_repo_finish(update, context):
    user_id = update.message.from_user.id
    repo_name = update.message.text
    user_data = get_user_data(user_id)

    tracked_repos = user_data.get('tracked_repos', {})
    if repo_name in tracked_repos:
        del tracked_repos[repo_name]
        set_user_data(user_id, {'tracked_repos': tracked_repos})
        await update.message.reply_text(f"Stopped tracking {repo_name}.")
    else:
        await update.message.reply_text(f"You are not currently tracking {repo_name}.")
    return ConversationHandler.END

async def list_tracked_repos(update, context):
    user_id = update.message.from_user.id
    user_data = get_user_data(user_id)
    tracked_repos = user_data.get('tracked_repos', {})
    if not tracked_repos:
        return await update.message.reply_text("You are not tracking any repositories.")

    repo_list = "\n".join([f"- {repo}" for repo in tracked_repos.keys()])
    await update.message.reply_text(f"You are tracking the following repositories:\n{repo_list}")

async def check_new_pull_requests(context: ContextTypes.DEFAULT_TYPE):
    if not db: return
    users_ref = db.collection('users').stream()
    for user_doc in users_ref:
        user_id, user_data = user_doc.id, user_doc.to_dict()
        if not user_data.get('tracked_repos'): continue

        g = Github(user_data.get('github_token'))
        for repo_name, tracking_data in user_data['tracked_repos'].items():
            try:
                repo = g.get_repo(repo_name)
                last_pr_number = tracking_data.get('last_pr_number', 0)
                pulls = repo.get_pulls(state='open', sort='created', direction='desc')
                newest_pr_in_batch = last_pr_number
                new_prs = []

                for pull in pulls:
                    if pull.number > last_pr_number:
                        new_prs.append(pull)
                        newest_pr_in_batch = max(newest_pr_in_batch, pull.number)
                    else: break
                
                for pull in reversed(new_prs):
                    message = (
                        f"🚀 New Pull Request in {repo_name}\n\n" 
                        f"#{pull.number} {pull.title}\n" 
                        f"by {pull.user.login}\n\n" 
                        f"{pull.html_url}"
                    )
                    await context.bot.send_message(chat_id=user_id, text=message)
                
                if newest_pr_in_batch > last_pr_number:
                    user_data['tracked_repos'][repo_name]['last_pr_number'] = newest_pr_in_batch
                    set_user_data(user_id, {'tracked_repos': user_data['tracked_repos']})

            except Exception as e:
                print(f"Error checking PRs for {user_id} in {repo_name}: {e}")

# --- Settings Update Handlers ---
async def set_token_start(update, context):
    await update.message.reply_text("Please enter your new GitHub personal access token.")
    return UPDATE_TOKEN

async def update_token(update, context):
    set_user_data(update.message.from_user.id, {'github_token': update.message.text})
    await update.message.reply_text("GitHub token updated successfully.")
    return ConversationHandler.END

async def set_repo_start(update, context):
    await update.message.reply_text("Enter the new primary repository name (username/repo).")
    return UPDATE_REPO

async def update_repo(update, context):
    set_user_data(update.message.from_user.id, {'repo_name': update.message.text})
    await update.message.reply_text("Primary repository updated successfully.")
    return ConversationHandler.END

async def cancel(update, context):
    context.user_data.clear()
    await update.message.reply_text('Operation cancelled.')
    return ConversationHandler.END

# --- Main Bot Setup ---
async def main():
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Set up the job queue for background tasks
    job_queue = application.job_queue
    job_queue.run_repeating(check_new_pull_requests, interval=300, first=10)

    # Conversation handlers
    conv_defs = {
        "setup": (start, {ASK_TOKEN: [ask_repo_for_setup], ASK_REPO: [set_repo_and_finish_setup]}),
        "update_token": (set_token_start, {UPDATE_TOKEN: [update_token]}),
        "update_repo": (set_repo_start, {UPDATE_REPO: [update_repo]}),
        "track": (track_repo_start, {TRACK_REPO: [track_repo_finish]}),
        "untrack": (untrack_repo_start, {UNTRACK_REPO: [untrack_repo_finish]}),
    }
    for name, entry_point in conv_defs.items():
        entry_handler, states_handlers = entry_point
        application.add_handler(ConversationHandler(
            entry_points=[CommandHandler(name, entry_handler)],
            states={state: [MessageHandler(filters.TEXT & ~filters.COMMAND, cb)] for state, cbs in states_handlers.items() for cb in cbs},
            fallbacks=[CommandHandler('cancel', cancel)],
            conversation_timeout=60
        ))

    # Command handlers
    application.add_handler(CommandHandler("random_review", random_review))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("tracked", list_tracked_repos))
    
    # Run the bot until the user presses Ctrl-C
    try:
        print("Starting bot...")
        await application.initialize()
        await application.start()
        await application.updater.start_polling()
        # Keep the bot running
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        print("Stopping bot...")
    finally:
        if application.updater.is_polling():
            await application.updater.stop()
        await application.stop()
        await application.shutdown()

if __name__ == '__main__':
    asyncio.run(main())
