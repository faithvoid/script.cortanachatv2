import os
import xbmc
import xbmcgui

GAMES_TXT = xbmc.translatePath('special://home/games.txt')

def clean_game_name(folder_name):
    """Remove bracketed text and clean up the folder name."""
    import re
    return re.sub(r"\s*\(.*?\)", "", folder_name).strip()

def browse_for_xbe():
    """Open a file browser to select a default.xbe file."""
    dialog = xbmcgui.Dialog()
    xbe_path = dialog.browse(1, 'Select default.xbe', 'files', 'default.xbe', False, False, 'F:\\Games')
    return xbe_path if xbe_path.endswith('default.xbe') else None

def get_folder_name_from_path(path):
    """Extract folder name from full path."""
    return os.path.basename(os.path.dirname(path))

def get_game_name(folder_name):
    """Prompt user to confirm or edit the game name."""
    clean_name = clean_game_name(folder_name)
    dialog = xbmcgui.Dialog()
    keyboard = xbmc.Keyboard(clean_name, "Enter Game Name")
    keyboard.doModal()
    if keyboard.isConfirmed():
        return keyboard.getText()
    return None

def write_to_games_txt(game_name, xbe_path):
    """Append the game entry to games.txt, ensuring proper formatting."""
    entry = '\"%s\", \"%s\"' % (game_name, xbe_path)

    try:
        # Read the file first to check if it ends with a newline
        if os.path.exists(GAMES_TXT):
            with open(GAMES_TXT, "rb") as f:  # Open in binary mode to read raw bytes
                f.seek(-1, os.SEEK_END)  # Go to the last byte
                last_char = f.read(1)

            # If the last character is not a newline, fix it
            if last_char != b"\n":
                with open(GAMES_TXT, "ab") as f:  # Append in binary mode
                    f.write("\n")

        # Append new entry
        with open(GAMES_TXT, "a") as f:  # Open in standard append mode
            f.write(entry + "\n")

    except Exception as e:
        xbmcgui.Dialog().ok("Error", "Failed to write to games.txt:\n%s" % str(e))

def main():
    xbe_path = browse_for_xbe()
    if not xbe_path:
        xbmcgui.Dialog().ok("Error", "No default.xbe selected!")
        return
    
    folder_name = get_folder_name_from_path(xbe_path)
    game_name = get_game_name(folder_name)
    
    if game_name:
        write_to_games_txt(game_name, xbe_path)
        xbmcgui.Dialog().ok("Success", "Game added to games.txt!")
    else:
        xbmcgui.Dialog().ok("Cancelled", "No game name entered.")

if __name__ == "__main__":
    main()
