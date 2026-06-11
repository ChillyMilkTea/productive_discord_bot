import discord
from discord.ext import commands
import logging 
from dotenv import load_dotenv
import os
import datetime
import asyncio

load_dotenv()
token = os.getenv('DISCORD_TOKEN')
VOICE_AFTER_FIVE_HOUR = int(os.getenv('VOICE_AFTER_FIVE_HOUR', '17'))
VOICE_TIMEZONE = os.getenv('VOICE_AFTER_FIVE_TZ')

handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True

bot = commands.Bot(command_prefix='!', intents=intents)

secret_role = "Gamer"
voice_after_five_counts = {}
voice_undeafen_tasks = {}


async def schedule_undeafen(member_id: int, guild_id: int, expires_at: datetime.datetime):
    """Sleep until `expires_at` and then attempt to undeafen the member.

    Stores include both the asyncio Task and the expiry so other handlers can
    re-jail members who rejoin before expiry without creating duplicate timers.
    """
    try:
        now = current_local_time()
        sleep_seconds = max(0, (expires_at - now).total_seconds())
        await asyncio.sleep(sleep_seconds)

        guild = bot.get_guild(guild_id)
        if guild is None:
            return
        member = guild.get_member(member_id)
        if member is None:
            return

        try:
            await member.edit(deafen=False)
            logging.info("Undeafened member %s at scheduled time", member)
        except discord.Forbidden:
            logging.warning("Missing permission to undeafen member %s", member)
        except Exception:
            logging.exception("Failed to undeafen member %s", member)
    finally:
        # Clear task reference when done or cancelled
        voice_undeafen_tasks.pop(member_id, None)

def current_local_time():
    if VOICE_TIMEZONE:
        from zoneinfo import ZoneInfo
        return datetime.datetime.now(ZoneInfo(VOICE_TIMEZONE))
    return datetime.datetime.now()


def check_voice_after_five(member, now=None):
    """Track how many times a member has joined voice after 5pm local time.

    The counter resets when the day changes.
    """
    if now is None:
        now = current_local_time()
    today = now.date()
    data = voice_after_five_counts.get(member.id)

    if data is None or data["date"] != today:
        data = {"date": today, "count": 0}

    if now.hour >= VOICE_AFTER_FIVE_HOUR:
        data["count"] += 1
        voice_after_five_counts[member.id] = data
        return data["count"]

    voice_after_five_counts[member.id] = data
    return 0


@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')


async def habitJail(member, before, after):
    """Move members to 'habitJail' if they change voice state after 5pm local time."""
    
    now = current_local_time()
    try:
        if now.hour >= VOICE_AFTER_FIVE_HOUR:
            # Find the voice channel named 'habitJail'
            habit_jail = discord.utils.get(member.guild.voice_channels, name='habitJail')
            if habit_jail is None:
                logging.debug("habitJail channel not found in guild %s", member.guild)
                return
            
            # Hierarchy check FIRST to ensure bot can move the member
            bot_member = member.guild.me
            if member.top_role >= bot_member.top_role or member.id == bot_member.id:
                print(f"Cannot moderate {member.name} due to hierarchy rules.")
                return
            
            # Check if bot has required permissions to deafen
            if not bot_member.guild_permissions.deafen_members:
                print(f"Bot missing 'Deafen Members' permission in guild {member.guild.name}")
                return
            
            # Only attempt move if user isn't already in habit_jail and then deafen
            if after.channel is not None and after.channel != habit_jail:
                await member.move_to(habit_jail)
                await member.edit(deafen=True)
                try:
                    text_channel = discord.utils.get(member.guild.text_channels, name='habitJail')
                    if text_channel:
                        await text_channel.send(
                            f"{member.mention} has been moved to habitJail starting at {current_local_time().strftime('%Y-%m-%d %H:%M')}."
                        )
                    else:
                        logging.debug("habitJail text channel not found in guild %s", member.guild)
                except discord.Forbidden:
                    logging.warning("Bot lacks permission to send messages in habitJail channel for guild %s", member.guild)
                except Exception:
                    logging.exception("Failed to notify habitJail channel for %s", member)
                # Schedule undeafen after one hour (3600s) if not already scheduled.
                existing = voice_undeafen_tasks.get(member.id)
                if not existing:
                    expires_at = current_local_time() + datetime.timedelta(seconds=3600)
                    task = asyncio.create_task(schedule_undeafen(member.id, member.guild.id, expires_at))
                    voice_undeafen_tasks[member.id] = {"task": task, "expires_at": expires_at}


    except Exception:
        logging.exception("Failed to move member %s to habitJail", member)


@bot.event
async def on_voice_state_update(member, before, after):
    if before.channel is None and after.channel is not None:
        now = current_local_time()
        joins_after_five = check_voice_after_five(member, now)

        # If there's an active undeafen timer for this member and it hasn't expired,
        # re-jail them for the remaining time.
        entry = voice_undeafen_tasks.get(member.id)
        if entry:
            expires_at = entry.get("expires_at") if isinstance(entry, dict) else None
            if expires_at and expires_at > now:
                remaining = (expires_at - now).total_seconds()
                print(f"{member} rejoined with active timer; remaining={int(remaining)}s. Re-jailing for remaining time.")
                # Call habitJail which will move and deafen the member (it will NOT create a new timer)
                await habitJail(member, before, after)
                return

        if joins_after_five == 1:
            print(f"{member} joined voice at {now.strftime('%H:%M')} local time; count={joins_after_five}. Jailing...")
            await habitJail(member, before, after)
        elif joins_after_five > 1:
            print(f"{member} joined voice at {now.strftime('%H:%M')} local time; count={joins_after_five}. No action taken.")
        else:
            print(f"{member} joined voice at {now.strftime('%H:%M')} local time, before {VOICE_AFTER_FIVE_HOUR}:00. Not counted.")

    elif before.channel is not None and after.channel is None:
        print(f"Not first time {member} joined a voice channel, skipping habitJail check.")

bot.run(token, log_handler=handler, log_level=logging.DEBUG)