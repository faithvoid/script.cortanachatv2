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
    login_file = xbmc.translatePath('special://home/userdata/profiles/{}/login.txt'.format(xbmc.getInfoLabel('System.ProfileName')))
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

# Fetch home feed
def fetch_home_feed(session, cursor=None):
    url = BASE_URL + 'app.bsky.feed.getTimeline'
    headers = {'Authorization': 'Bearer ' + session['accessJwt']}
    params = {'limit': 25}
    if cursor:
        params['cursor'] = cursor
    
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        feed = data.get('feed', [])
        next_cursor = data.get('cursor', None)
        
        dids = {post['post']['author']['did'] for post in feed if 'post' in post and 'author' in post['post'] and 'did' in post['post']['author']}
        profiles = fetch_profiles(session, dids)
        
        for post in feed:
            author = post.get('post', {}).get('author', {})
            if 'did' in author:
                author['handle'] = profiles.get(author['did'], 'Unknown')
        
        return feed, next_cursor
    except requests.exceptions.RequestException as e:
        xbmcgui.Dialog().ok('xSky', 'Failed to fetch home feed: ' + str(e))
        return [], None

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

# Fetch user profiles in bulk
def fetch_profiles(session, dids):
    profiles = {}
    for did in dids:
        profiles[did] = fetch_profile(session, did)
    return profiles

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

# Fetch conversations with proper user handles in bulk
def fetch_conversations(session):
    url = CHAT_URL + 'chat.bsky.convo.listConvos'
    headers = {'Authorization': 'Bearer ' + session['accessJwt']}
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        conversations = response.json().get('convos', [])
        
        # Collect all unique DIDs to fetch in bulk
        dids = {participant['did'] for convo in conversations for participant in convo.get('members', []) if 'did' in participant}
        profiles = {did: fetch_profile(session, did) for did in dids}
        
        # Assign resolved handles to conversations
        for convo in conversations:
            participants = convo.get('members', [])
            for participant in participants:
                if 'did' in participant:
                    participant['handle'] = profiles.get(participant['did'], 'Unknown')
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

# Create a new post
def create_post(session):
    keyboard = xbmc.Keyboard('', 'Enter your post')
    keyboard.doModal()
    if keyboard.isConfirmed():
        post_text = keyboard.getText()
        
        # trailing "Z" is preferred over "+00:00"
        now = datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
        
        # Detect facets for hashtags and mentions
        facets = detect_facets(post_text, session)

        post = {
            "$type": "app.bsky.feed.post",
            "text": post_text,
            "facets": facets,
            "createdAt": now,
        }

        url = BASE_URL + 'com.atproto.repo.createRecord'
        headers = {
            'Authorization': 'Bearer ' + session['accessJwt']
        }
        data = {
            'repo': session['did'],
            'collection': 'app.bsky.feed.post',
            'record': post
        }
        try:
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()  # Raise an error for bad status codes
            xbmcgui.Dialog().ok('Cortana Chat', 'Post created successfully!')
        except requests.exceptions.RequestException as e:
            xbmcgui.Dialog().ok('Cortana Chat', 'Failed to create post. Error: {}'.format(str(e)))

# Create a new post with media
def create_post_media(session):
    keyboard = xbmc.Keyboard('', 'Enter your post')
    keyboard.doModal()
    if keyboard.isConfirmed():
        post_text = keyboard.getText()
        
        # trailing "Z" is preferred over "+00:00"
        now = datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
        
        # Detect facets for hashtags and mentions
        facets = detect_facets(post_text, session)

        # Prompt user to select image files
        dialog = xbmcgui.Dialog()
        image_paths = []
        while True:
            image_path = dialog.browse(1, 'Select Image', 'files', '.jpg|.jpeg|.png|.webp', False, False, '')
            if image_path:
                image_paths.append(image_path)
                if len(image_paths) >= 4:  # Limit to 4 images
                    break
                if not dialog.yesno('Cortana Chat', 'Do you want to add another image?'):
                    break
            else:
                break

        # Upload images and prepare the media structure
        images = []
        for image_path in image_paths:
            with open(image_path, 'rb') as f:
                img_bytes = f.read()
            # this size limit is specified in the app.bsky.embed.images lexicon
            if len(img_bytes) > 1000000:
                xbmcgui.Dialog().ok('Cortana Chat', 'Image file size too large. 1000000 bytes (1MB) maximum, got: {}'.format(len(img_bytes)))
                return
            blob = upload_file(BASE_URL, session['accessJwt'], image_path, img_bytes)
            images.append({"alt": "", "image": blob})

        post = {
            "$type": "app.bsky.feed.post",
            "text": post_text,
            "facets": facets,
            "createdAt": now,
            "embed": {
                "$type": "app.bsky.embed.images",
                "images": images
            }
        }

        url = BASE_URL + 'com.atproto.repo.createRecord'
        headers = {
            'Authorization': 'Bearer ' + session['accessJwt']
        }
        data = {
            'repo': session['did'],
            'collection': 'app.bsky.feed.post',
            'record': post
        }
        try:
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()  # Raise an error for bad status codes
            xbmcgui.Dialog().ok('Cortana Chat', 'Post created successfully!')
        except requests.exceptions.RequestException as e:
            xbmcgui.Dialog().ok('Cortana Chat', 'Failed to create post. Error: {}'.format(str(e)))

# Function to upload files
def upload_file(base_url, access_token, filename, img_bytes):
    suffix = filename.split(".")[-1].lower()
    mimetype = "application/octet-stream"
    if suffix in ["png"]:
        mimetype = "image/png"
    elif suffix in ["jpeg", "jpg"]:
        mimetype = "image/jpeg"
    elif suffix in ["webp"]:
        mimetype = "image/webp"

    resp = requests.post(
        base_url + "com.atproto.repo.uploadBlob",
        headers={
            "Content-Type": mimetype,
            "Authorization": "Bearer " + access_token,
        },
        data=img_bytes,
    )
    resp.raise_for_status()
    return resp.json()["blob"]

# Detects mention / tag facets and hyperlinks them accordingly.
def detect_facets(text, session):
    facets = []
    utf16_text = text

    def utf16_index_to_utf8_index(i):
        return len(utf16_text[:i].encode('utf-8'))

    # Detect mentions
    mention_pattern = re.compile(r'(^|\s|\()(@[a-zA-Z0-9.-]+)(\b)')
    for match in mention_pattern.finditer(utf16_text):
        mention = match.group(2)
        handle = mention[1:]  # Remove the '@' character
        start = match.start(2)
        end = match.end(2)
        did = resolve_did(handle, session)
        if did:
            facets.append({
                'index': {
                    'byteStart': utf16_index_to_utf8_index(start),
                    'byteEnd': utf16_index_to_utf8_index(end),
                },
                'features': [{
                    '$type': 'app.bsky.richtext.facet#mention',
                    'did': did
                }]
            })

    # Detect hashtags
    hashtag_pattern = re.compile(r'(#[^\d\s]\S*)')
    for match in hashtag_pattern.finditer(utf16_text):
        hashtag = match.group(1)
        start = match.start(1)
        end = match.end(1)
        facets.append({
            'index': {
                'byteStart': utf16_index_to_utf8_index(start),
                'byteEnd': utf16_index_to_utf8_index(end),
            },
            'features': [{
                '$type': 'app.bsky.richtext.facet#tag',
                'tag': hashtag[1:]
            }]
        })

    return facets

# Display menu
def display_menu(session):
    while True:
        dialog = xbmcgui.Dialog()
        options = ['Chat', 'Friends', 'Notifications', 'Settings']
        choice = dialog.select('Cortana Chat', options)
        if choice == -1:
            return  # User backed out
        elif choice == 0:
            display_conversations(session)
        elif choice == 1:
            display_friends_menu(session)
        elif choice == 2:
            display_notifications(session)
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
        options = ['Enable Notifications', 'Disable Notifications', 'Follow User', 'Block User', 'Install Game']
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
        elif choice == 4:
            install_game()

# Display home feed
def display_home_feed(session):
    cursor = None
    while True:
        feed, next_cursor = fetch_home_feed(session, cursor)
        items = ["Post", "Post Media"]  # New options for posting
        items += [post['post']['author'].get('handle', 'Unknown') + ': ' + post['post']['record'].get('text', 'No content') 
                  for post in feed if 'post' in post and 'author' in post['post'] and 'record' in post['post']]

        if next_cursor:
            items.append("Next Page")

        dialog = xbmcgui.Dialog()
        choice = dialog.select("Home Feed", items)

        if choice == -1:
            break  # User backed out
        elif choice == 0:
            create_post(session)  # Call function to create a post
        elif choice == 1:
            create_post_media(session)  # Call function to create a post with media
        elif next_cursor and choice == len(items) - 1:
            cursor = next_cursor  # Load next page
        else:
            selected_post = feed[choice - 2].get("post", {})  # Adjust for added options
            author_handle = selected_post.get("author", {}).get("handle", "Unknown")
            post_text = selected_post.get("record", {}).get("text", "No content")
            xbmcgui.Dialog().ok(author_handle, post_text)

# Fetch post content by URI
def fetch_post_content(session, uri):
    url = BASE_URL + "app.bsky.feed.getPosts"
    headers = {"Authorization": "Bearer " + session["accessJwt"]}
    params = {"uris": uri}

    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        posts = response.json().get("posts", [])
        if posts:
            return posts[0].get("record", {}).get("text", "No content")
    except requests.exceptions.RequestException:
        return "Failed to load content"

    return "No content"

# Display notifications with post content
def display_notifications(session):
    notifications = fetch_notifications(session)
    items = []

    for n in notifications:
        author = n.get("author", {}).get("handle", "Unknown")
        reason = n.get("reason", "Unknown")
        text = n.get("record", {}).get("text", "")

        # Fetch referenced post content if it's a like or repost
        if reason in ["like", "repost"]:
            post_uri = n.get("reasonSubject", "")
            text = fetch_post_content(session, post_uri) if post_uri else "No content"

        items.append("{} - {} - {}".format(reason, author, text))

    xbmcgui.Dialog().select("Notifications", items)

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
    items = ['Reply', 'Nudge', 'Invite To Game'] + [m.get('sender', {}).get('handle', 'Unknown') + ': ' + m.get('text', '') for m in messages]
    dialog = xbmcgui.Dialog()
    choice = dialog.select('Messages', items)
    
    if choice == -1:
        display_conversations(session)  # User backed out
    elif choice == 0:
        reply_to_conversation(session, convo_id)
    elif choice == 1:
        send_nudge(session, convo_id)
    elif choice == 2:
        invite_to_game(session, convo_id)
    elif choice > 2:
        message_text = messages[choice - 3].get('text', '')
        match = re.match(r"(.*) would like to play '(.*)'", message_text)
        if match:
            game_title = match.group(2)
            display_message_options(session, convo_id, game_title)

# Display message options
def display_message_options(session, convo_id, game_title):
    dialog = xbmcgui.Dialog()
    options = ['Reply', 'Accept Invite', 'Decline Invite']
    choice = dialog.select('Message Options', options)
    if choice == 0:
        reply_to_conversation(session, convo_id)
    elif choice == 1:
        launch_game(game_title)
    elif choice == 2:
        display_messages(session, convo_id)

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

# Nudge function
def send_nudge(session, convo_id):
    nudge_text = session['handle'] + " has sent you a nudge!"
    now = datetime.datetime.utcnow().isoformat() + 'Z'
    message = {'$type': 'chat.bsky.convo.message', 'text': nudge_text, 'createdAt': now}
    url = CHAT_URL + 'chat.bsky.convo.sendMessage'
    headers = {'Authorization': 'Bearer ' + session['accessJwt']}
    data = {'convoId': convo_id, 'message': message}
    
    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        xbmcgui.Dialog().ok('xSky', 'Nudge sent successfully!')
    except requests.exceptions.RequestException as e:
        xbmcgui.Dialog().ok('xSky', 'Failed to send nudge: ' + str(e))

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
    games_file = xbmc.translatePath('special://home/games.txt')
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
        dialog = xbmcgui.Dialog()
        choice = dialog.yesno('Game Not Found', '' + game_title + ' not found. Would you like to locate it?')
        if choice:
            install_game(game_title)

# Clean game name by removing bracketed text
def clean_game_name(folder_name):
    return re.sub(r"\s*\(.*?\)", "", folder_name).strip()

# Prompt user to browse for XBE file
def browse_for_xbe():
    dialog = xbmcgui.Dialog()
    xbe_path = dialog.browse(1, 'Select default.xbe', 'files', 'default.xbe', False, False)
    return xbe_path if xbe_path.endswith('default.xbe') else None

# Extract folder name from path
def get_folder_name_from_path(path):
    return os.path.basename(os.path.dirname(path))

# Prompt user to confirm or edit the game name
def get_game_name(default_name):
    clean_name = clean_game_name(default_name)
    keyboard = xbmc.Keyboard(clean_name, "Enter Game Name")
    keyboard.doModal()
    return keyboard.getText() if keyboard.isConfirmed() else None

# Write game entry to games.txt
def write_to_games_txt(game_name, xbe_path):
    games_file = xbmc.translatePath('special://home/games.txt')
    entry = '"{}", "{}"\n'.format(game_name, xbe_path)

    try:
        # Ensure the file ends with a newline
        if os.path.exists(games_file):
            with open(games_file, "rb") as f:
                f.seek(-1, os.SEEK_END)
                last_char = f.read(1)
            if last_char != b"\n":
                with open(games_file, "ab") as f:
                    f.write(b"\n")

        # Append new entry
        with open(games_file, "a") as f:
            f.write(entry)

    except Exception as e:
        xbmcgui.Dialog().ok("Error", "Failed to write to games.txt:\n{}".format(str(e)))

# Install a game
def install_game(game_title=None):
    xbe_path = browse_for_xbe()
    if not xbe_path:
        xbmcgui.Dialog().ok("Error", "No default.xbe selected!")
        return

    folder_name = get_folder_name_from_path(xbe_path)
    game_name = get_game_name(game_title if game_title else folder_name)

    if game_name:
        write_to_games_txt(game_name, xbe_path)
        
        # Combine success and launch prompt into one dialog
        launch_choice = xbmcgui.Dialog().yesno("Game Added", "{} has been installed!".format(game_name), "Would you like to launch it now?")

        if launch_choice:
            launch_game(game_name)
    else:
        xbmcgui.Dialog().ok("Cancelled", "No game name entered.")

# Enable notifications
def enable_notifications():
    script_path = os.path.join(os.path.dirname(__file__), 'notifier.py')
    xbmc.executebuiltin('RunScript("{}")'.format(script_path.replace("\\", "\\\\")))

# Disable notifications
def disable_notifications():
    script_path = os.path.join(os.path.dirname(__file__), 'stop_notifier.py')
    xbmc.executebuiltin('RunScript("{}")'.format(script_path.replace("\\", "\\\\")))

# Main function with direct menu navigation
def main():
    username, app_password = load_credentials()
    if not username or not app_password:
        xbmcgui.Dialog().ok('xSky', 'Enter your BlueSky username and app password in login.txt.')
        return

    session = authenticate(username, app_password)
    if not session:
        return

    # Check for arguments passed from XBMC
    if len(sys.argv) > 1:
        option = sys.argv[1]
        if option == "Chat":
            display_conversations(session)
        elif option == "Notifications":
            display_notifications(session)
        elif option == "Friends":
            display_friends_menu(session)
        elif option == "Activity":
            display_home_feed(session)
        elif option == "Settings":
            display_settings_menu(session)

        else:
            display_menu(session)
    else:
        display_menu(session)

if __name__ == '__main__':
    main()
