# Cortana Chat (Script Edition) - Bluesky / AT Protocol based instant messaging client for XBMC4Xbox

A functional, decentralized and easy to use instant messenger, right on your Xbox.

![icon](icon.png)

## Screenshots:
![Menu](screenshots/mainmenu.png)
![Conversations](screenshots/conversations.png)
![Messages](screenshots/messages.png)
![Invite](screenshots/invite.png)
![Friends](screenshots/friends.png)
![Followers](screenshots/followers.png)
![Following](screenshots/following.png)
![Notifications](screenshots/notifications.png)
![Settings](screenshots/settings.png)

## Install:
- Before downloading, make sure you're on XBMC 3.6-DEV-r33046 or later, as this most likely requires up to date TLS/SSL libraries!
- Download latest release .zip
- Extract the .zip file and edit "login.txt" to contain your full username (ie; username.bsky.social or username.custom.domain) and app password (do not use your actual password!)
- Edit "default.py" and modify "TIMEZONE_OFFSET = -5" to your local timezone relative to UTC (-5 is EST) for accurate timestamps
- Copy the Cortana Chat folder to Q:/scripts, but copy your login.txt to your user profile (usually under Q:/UserData/profiles/). You can do this for all the profiles on your system to give them all individual social features!
- (Optional) if using a non-Bluesky AT protocol site, you'll have to modify the BASE_URL and CHAT_URL in default.py to point at that site! Support outside of Bluesky is entirely unsupported, but testing & contributing is encouraged!
- Run the add-on and enjoy!

## Working
- TBA, but it IS working!

## Not Working
- TBA

## TODO:
- TBA
