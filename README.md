# Command-Editor
Use Py3.8 branch for Windows 7

Streamlabs Chatbot Commands feature replacement for those who use Windows 7 (or Linux)

One of my friends is still using windows 7 and his Streamlabs Chatbot stopped connecting to Twitch, so I made this app.

This was coded using AI as experiment, most of the features might not work or do unexpected stuff

Features:
- StreamLabs Chatbot Command Backup compatible (but will not work for streamlabs import)
- Auto-assign sound files from folder with same name as commands
- Working cooldown and volume configuration
- Response as bot account
- Add/Remove commands
- Twitch chat for commands
- Auto-save each 300s and on exit.

Known issues:
- Every textbox change doesn't change the table (only volume works)
- Adding/Removing Commands while bot is connected to channel will crash software
- Commands without "!" will not work.
- On first twitch setup bot thinks that there's no config for twitch, after restart it will work (because config is created and saved)
- This code is trash
- There's no support for custom response commands, that include usage of Twitch API

Fork the code if you want to change it
