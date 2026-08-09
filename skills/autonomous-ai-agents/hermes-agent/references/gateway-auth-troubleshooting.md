# Hermes Gateway Authentication Troubleshooting

## Common Authentication Errors

### Telegram: "Unauthorized" when sending messages
**Cause:** Invalid or missing bot token
**Solution:**
1. Verify your bot token from @BotFather
2. Run `hermes gateway setup` → select Telegram
3. Or set directly: `hermes config set gateway.telegram.bot_token YOUR_TOKEN`
4. Restart gateway: `hermes gateway restart`

### Discord: "Improper token has been passed"
**Cause:** Invalid bot token or missing Message Content Intent
**Solution:**
1. Verify bot token from Discord Developer Portal
2. Ensure Message Content Intent is enabled in Bot Settings → Privileged Gateway Intents
3. Run `hermes gateway setup` → select Discord
4. Restart gateway: `hermes gateway restart`

### General Authentication Issues
**Steps to diagnose:**
1. Check gateway logs: `grep -i "failed to send\\|error" ~/.hermes/logs/gateway.log | tail -20`
2. Look for "Unauthorized" or "LoginFailure" messages
3. Verify credentials in `~/.hermes/.env`:
   - `TELEGRAM_BOT_TOKEN`
   - `DISCORD_BOT_TOKEN`
   - Other platform-specific tokens
4. Reconfigure via setup wizard: `hermes gateway setup`
5. Restart gateway after changes

**Environment Variable Format:**
In `~/.hermes/.env`:
```
TELEGRAM_BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
DISCORD_BOT_TOKEN=MjM2... (long string)
```

**Quick Fix Commands:**
```bash
# Check current config
hermes config get gateway.telegram.bot_token
hermes config get gateway.discord.bot_token

# Set new tokens
hermes config set gateway.telegram.bot_token "your_telegram_token"
hermes config set gateway.discord.bot_token "your_discord_token"

# Restart service
hermes gateway restart
```

**Verification:**
After restart, check gateway status:
```bash
hermes gateway status
# Should show active (running) without authentication errors
```