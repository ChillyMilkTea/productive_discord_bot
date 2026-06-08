import discord
from discord.ext import commands
import logging 
from dotenv import load_dotenv
import os
import datetime

load_dotenv()
token = os.getenv('DISCORD_TOKEN')

handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True

bot = commands.Bot(command_prefix='!', intents=intents)

secret_role = "Gamer"

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')


@bot.event
async def habitJail(member, before, after):
    """Move members to 'habitJail' if they change voice state after 5pm local time."""
    
    now = datetime.datetime.now()
    try:
        if now.hour >= 17:
            # Find the voice channel named 'habitJail'
            habit_jail = discord.utils.get(member.guild.voice_channels, name='habitJail')
            if habit_jail is None:
                logging.debug("habitJail channel not found in guild %s", member.guild)
                return
            # Only attempt move if user isn't already in habit_jail
            if after.channel is not None and after.channel != habit_jail:
                await member.move_to(habit_jail)
                await member.edit(mute=True)
            # hierarchy check to ensure bot can move the member
            bot_member = member.guild.me
            if member.top_role >= bot_member.top_role or member.id == bot_member.id:
                print(f"Cannot moderate {member.name} due to hierarchy rules.")
                return
            
            # deafen user in habit_jail <- looks like this code is the issue here, has to do with roles and permissions, I'll need someone to troubleshoot in discord since I'm the admin of the server
            # if after.channel == habit_jail:
            #     await member.edit(mute=True)

    except Exception:
        logging.exception("Failed to move member %s to habitJail", member)


@bot.event
async def on_voice_state_update(member, before, after):
    if before.channel is None and after.channel is not None:
        await habitJail(member, before, after)
    elif before.channel is not None and after.channel is None:
        print(f"Not first time {member} joined a voice channel, skipping habitJail check.")
        

bot.run(token, log_handler=handler, log_level=logging.DEBUG)