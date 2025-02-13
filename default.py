import xbmc
import xbmcgui
import requests
import os
import sys
import json
import datetime
import re
from datetime import timedelta

# BlueSky API endpoints
BASE_URL = 'https://bsky.social/xrpc/'
CHAT_URL = 'https://api.bsky.chat/xrpc/'

# Load login credentials
def load_credentials():
    login_file = os.path.join(os.path.dirname(__file__), 'login.txt')
    if os.path.exists(login_file):
        with open(login_file, 'r') as f:
            lines = f.readlines()
            if len(lines) >= 2:
                return lines[0].strip(), lines[1].strip()
    return None, None

# Authenticate with BlueSky
def authenticate(username, app_password):
    url = BASE_URL + 'com.atproto.server.createSession'
    data = {'identifier': username, 'password': app_password}
    try:
        response = requests.post(url, json=data)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        xbmcgui.Dialog().ok('xSky', 'Authentication failed: ' + str(e))
        return None

# Fetch user profile to resolve handle
def fetch_profile(session, did):
    url = BASE_URL + 'app.bsky.actor.getProfile'
    headers = {'Authorization': 'Bearer ' + session['accessJwt']}
    params = {'actor': did}
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json().get('handle', 'Unknown')
    except requests.exceptions.RequestException:
        return 'Unknown'

# Fetch notifications
def fetch_notifications(session):
    url = BASE_URL + 'app.bsky.notification.listNotifications'
    headers = {'Authorization': 'Bearer ' + session['accessJwt']}
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json().get('notifications', [])
    except requests.exceptions.RequestException as e:
        xbmcgui.Dialog().ok('xSky', 'Failed to fetch notifications: ' + str(e))
        return []

# Fetch followers
def fetch_followers(session):
    url = BASE_URL + 'app.bsky.graph.getFollowers'
    headers = {'Authorization': 'Bearer ' + session['accessJwt']}
    params = {'actor': session['handle']}
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json().get('followers', [])
    except requests.exceptions.RequestException as e:
        xbmcgui.Dialog().ok('xSky', 'Failed to fetch followers: ' + str(e))
        return []

# Fetch following
def fetch_following(session):
    url = BASE_URL + 'app.bsky.graph.getFollows'
    headers = {'Authorization': 'Bearer ' + session['accessJwt']}
    params = {'actor': session['handle']}
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json().get('follows', [])
    except requests.exceptions.RequestException as e:
        xbmcgui.Dialog().ok('xSky', 'Failed to fetch following: ' + str(e))
        return []

# Fetch conversations
def fetch_conversations(session):
    url = CHAT_URL + 'chat.bsky.convo.listConvos'
    headers = {'Authorization': 'Bearer ' + session['accessJwt']}
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        conversations = response.json().get('convos', [])
        
        for convo in conversations:
            participants = convo.get('members', [])
            for participant in participants:
                if 'handle' not in participant and 'did' in participant:
                    participant['handle'] = fetch_profile(session, participant['did'])
            convo['user_handle'] = next(
                (p['handle'] for p in participants if p['handle'] != session['handle']),
                'Unknown'
            )
        
        return conversations
    except requests.exceptions.RequestException as e:
        xbmcgui.Dialog().ok('xSky', 'Failed to fetch conversations: ' + str(e))
        return []

# Fetch messages for a conversation
def fetch_messages(session, convo_id):
    url = CHAT_URL + 'chat.bsky.convo.getMessages'
    headers = {'Authorization': 'Bearer ' + session['accessJwt']}
    params = {'convoId': convo_id}
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        messages = response.json().get('messages', [])
        
        # Collect all unique DIDs to fetch in bulk
        dids = {message['sender']['did'] for message in messages if 'sender' in message and 'did' in message['sender']}
        profiles = {did: fetch_profile(session, did) for did in dids}
        
        # Assign resolved handles to messages
        for message in messages:
            if 'sender' in message and 'did' in message['sender']:
                message['sender']['handle'] = profiles.get(message['sender']['did'], 'Unknown')
        
        return messages
    except requests.exceptions.RequestException as e:
        xbmcgui.Dialog().ok('xSky', 'Failed to fetch messages: ' + str(e))
        return []

# Display menu
def display_menu(session):
    while True:
        dialog = xbmcgui.Dialog()
        options = ['Notifications', 'Chat', 'Friends', 'Settings']
        choice = dialog.select('Cortana Chat', options)
        if choice == -1:
            return  # User backed out
        elif choice == 0:
            display_notifications(session)
        elif choice == 1:
            display_conversations(session)
        elif choice == 2:
            display_friends_menu(session)
        elif choice == 3:
            display_settings_menu(session)

# Display menu
def display_friends_menu(session):
    while True:
        dialog = xbmcgui.Dialog()
        options = ['Followers', 'Following', 'Follow User', 'Block User']
        choice = dialog.select('Friends', options)
        if choice == -1:
            return  # User backed out
        elif choice == 0:
            display_followers(session)
        elif choice == 1:
            display_following(session)
        elif choice == 2:
            follow_user(session)
        elif choice == 3:
            block_user(session)

# Display menu
def display_settings_menu(session):
    while True:
        dialog = xbmcgui.Dialog()
        options = ['Enable Notifications', 'Disable Notifications', 'Follow User', 'Block User']
        choice = dialog.select('Settings', options)
        if choice == -1:
            return  # User backed out
        elif choice == 0:
            enable_notifications()
        elif choice == 1:
            disable_notifications()
        elif choice == 2:
            follow_user(session)
        elif choice == 3:
            block_user(session)

# Display notifications
def display_notifications(session):
    notifications = fetch_notifications(session)
    items = [n.get('author', {}).get('handle', 'Unknown') + ': ' + n.get('record', {}).get('text', '') for n in notifications]
    xbmcgui.Dialog().select('Notifications', items)

# Display followers
def display_followers(session):
    followers = fetch_followers(session)
    items = [f.get('displayName', 'No Name') + ' (' + f.get('handle', 'Unknown') + ')' for f in followers]
    xbmcgui.Dialog().select('Followers', items)

# Display following
def display_following(session):
    following = fetch_following(session)
    items = [f.get('displayName', 'No Name') + ' (' + f.get('handle', 'Unknown') + ')' for f in following]
    xbmcgui.Dialog().select('Following', items)

# Display conversations
def display_conversations(session):
    conversations = fetch_conversations(session)
    items = [c.get('user_handle', 'Unknown') + ': ' + c.get('lastMessage', {}).get('text', 'No message') for c in conversations]
    dialog = xbmcgui.Dialog()
    choice = dialog.select('Conversations', items)
    if choice >= 0:
        convo_id = conversations[choice].get('id')
        display_messages(session, convo_id)

# Display messages in a conversation
def display_messages(session, convo_id):
    messages = fetch_messages(session, convo_id)
    items = ['Reply', 'Invite To Game'] + [m.get('sender', {}).get('handle', 'Unknown') + ': ' + m.get('text', '') for m in messages]
    dialog = xbmcgui.Dialog()
    choice = dialog.select('Messages', items)
    
    if choice == -1:
         display_conversations(session) # User backed out
    if choice == 0:
        reply_to_conversation(session, convo_id)
    elif choice == 1:
        invite_to_game(session, convo_id)
    elif choice > 1:
        message_text = messages[choice - 2].get('text', '')
        match = re.match(r"(.*) would like to play '(.*)'", message_text)
        if match:
            game_title = match.group(2)
            display_message_options(session, convo_id, game_title)

# Display message options
def display_message_options(session, convo_id, game_title):
    dialog = xbmcgui.Dialog()
    options = ['Reply', 'Accept Invite']
    choice = dialog.select('Message Options', options)
    if choice == 0:
        reply_to_conversation(session, convo_id)
    elif choice == 1:
        launch_game(game_title)

# Reply to a conversation and return to message list
def reply_to_conversation(session, convo_id):
    keyboard = xbmc.Keyboard('', 'Enter your reply')
    keyboard.doModal()
    if keyboard.isConfirmed():
        reply_text = keyboard.getText()
        now = datetime.datetime.utcnow().isoformat() + 'Z'
        message = {'$type': 'chat.bsky.convo.message', 'text': reply_text, 'createdAt': now}
        url = CHAT_URL + 'chat.bsky.convo.sendMessage'
        headers = {'Authorization': 'Bearer ' + session['accessJwt']}
        data = {'convoId': convo_id, 'message': message}
        try:
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()
            xbmcgui.Dialog().ok('xSky', 'Reply sent successfully!')
        except requests.exceptions.RequestException as e:
            xbmcgui.Dialog().ok('xSky', 'Failed to send reply: ' + str(e))
    display_messages(session, convo_id)

# Invite to a game
def invite_to_game(session, convo_id):
    games = load_games()
    if not games:
        xbmcgui.Dialog().ok('xSky', 'No games found in games.txt.')
        return
    
    dialog = xbmcgui.Dialog()
    selected_game = dialog.select('Select a game to invite', list(games.keys()))
    if selected_game >= 0:
        game_title = list(games.keys())[selected_game]
        reply_text = session['handle'] + " would like to play '" + game_title + "'"
        now = datetime.datetime.utcnow().isoformat() + 'Z'
        message = {'$type': 'chat.bsky.convo.message', 'text': reply_text, 'createdAt': now}
        url = CHAT_URL + 'chat.bsky.convo.sendMessage'
        headers = {'Authorization': 'Bearer ' + session['accessJwt']}
        data = {'convoId': convo_id, 'message': message}
        try:
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()
            xbmcgui.Dialog().ok('xSky', 'Invite sent successfully!')
	    return
        except requests.exceptions.RequestException as e:
            xbmcgui.Dialog().ok('xSky', 'Failed to send invite: ' + str(e))

# Load game paths
def load_games():
    games_file = os.path.join(os.path.dirname(__file__), 'games.txt')
    games = {}
    if os.path.exists(games_file):
        with open(games_file, 'r') as f:
            for line in f:
                parts = line.strip().split('", "')
                if len(parts) == 2:
                    games[parts[0].strip('"')] = parts[1].strip('"')
    return games

# Launch a game
def launch_game(game_title):
    games = load_games()
    if game_title in games:
        game_path = games[game_title]
        xbmc.executebuiltin('XBMC.RunXBE("' + game_path + '")')
        sys.exit()  # Ensures the script exits after launching the game
    else:
        xbmcgui.Dialog().ok('Error', 'Game not found: ' + game_title)

# Launch a game
def enable_notifications():
    script_path = os.path.join(os.path.dirname(__file__), 'notifier.py')
    xbmc.executebuiltin('RunScript("{}")'.format(script_path.replace("\\", "\\\\")))

# Main function
def main():
    username, app_password = load_credentials()
    if not username or not app_password:
        xbmcgui.Dialog().ok('xSky', 'Enter your BlueSky username and app password in login.txt.')
        return

    session = authenticate(username, app_password)
    if not session:
        return

    display_menu(session)

if __name__ == '__main__':
    main()
