# Command-Editor
Streamlabs Chatbot Commands feature replacement for those who use Windows 7 (or Linux)

One of my friends is still using windows 7 and his Streamlabs Chatbot stopped connecting to Twitch, so I made this app.

This was coded using AI as experiment, most of the features might not work or do unexpected stuff

Features:

- StreamLabs Chatbot Command Backup compatible (but will not work for streamlabs import)
- Auto-assign sound files from folder with same name as commands
- Working cooldown and volume configuration
- Response as bot account
- Add/Remove commands
- Twitch tab: chat for commands, viewers, stream status.
- Auto-save each 300s and on exit.
- Play/Stop Sound for testing volume
- Sound interruption toggle for twitch chat
- Sorting (Removed on v1.0.2h1 until properly tested)
- Search
- Backup manager
- Currency system
- Auto-reconnect
Known issues:

- Every textbox change doesn't change the table (only volume works)
- Adding/Removing Commands while bot is connected to channel will crash software (Not happening in release)
- Commands without "!" will not work.
- On first twitch setup bot thinks that there's no config for twitch, after restart it will work (because config is created and saved)
- Currency system has to be setup first, otherwise might not work
- Currency settings: command change not working, event bonus not working, sub bonus not working
- Ranks are not working
- This code is trash
- There's no support for custom response commands (as in StreamLabs)
Fork the code if you want to change it
