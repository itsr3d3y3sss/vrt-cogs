import datetime
import logging
from io import StringIO

import discord
from redbot.core import commands, Config

from .base import BaseCommands
from .commands import SupportCommands
from .persistview import start_button

log = logging.getLogger("red.vrt.support")


class Support(BaseCommands, SupportCommands, commands.Cog):
    """
    Support ticket system with buttons/logging
    """
    __author__ = "Vertyco"
    __version__ = "2.1.3"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        return f"{helpcmd}\nCog Version: {self.__version__}\nAuthor: {self.__author__}"

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        """No data to delete"""

    def __init__(self, bot, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot
        self.config = Config.get_conf(self, 117117, force_registration=True)
        default_guild = {
            # Ticket category
            "category": None,
            # Support button message data
            "message_id": None,
            "channel_id": None,
            "content": None,
            # Settings
            "enabled": False,
            "log": None,
            "support": [],
            "blacklist": [],
            "max_tickets": 1,
            "bcolor": "red",
            "embeds": False,
            # Ticket data
            "opened": {},
            "num": 0,
            # Content
            "button_content": "Click To Open A Ticket!",
            "emoji": None,
            "message": "{default}",
            "ticket_name": "{default}",
            # Toggles
            "dm": False,
            "user_can_rename": False,
            "user_can_close": True,
            "user_can_manage": False,
            "transcript": False,
            "auto_close": False,
        }
        self.config.register_guild(**default_guild)
        self.activeguilds = []

    # Add button components to support message and determine if a listener task needs to be created
    async def add_components(self):
        for guild in self.bot.guilds:
            if guild.id in self.activeguilds:
                continue
            conf = await self.config.guild(guild).all()
            if not conf["category"]:
                continue
            if not conf["message_id"]:
                continue
            if not conf["channel_id"]:
                continue
            channel = self.bot.get_channel(conf["channel_id"])
            if not channel:
                continue
            message = await channel.fetch_message(conf["message_id"])
            if not message:
                continue
            bcolor = conf["bcolor"]
            if bcolor == "red":
                style = discord.ButtonStyle.red
            elif bcolor == "blue":
                style = discord.ButtonStyle.blurple
            elif bcolor == "green":
                style = discord.ButtonStyle.green
            else:
                style = discord.ButtonStyle.grey
            button_content = conf["button_content"]
            emoji = conf["emoji"]
            await start_button(self.config, message, button_content, style, emoji)
            self.activeguilds.append(guild.id)

    # Clean up any ticket data that comes from a deleted channel or unknown user
    async def cleanup(self):
        for guild in self.bot.guilds:
            t = await self.config.guild(guild).opened()
            current_tickets = {}
            count = 0
            for uid, tickets in t.items():
                if not guild.get_member(int(uid)):
                    count += 1
                    continue
                new_tickets = {}
                for cid, data in tickets.items():
                    if not guild.get_channel(int(cid)):
                        count += 1
                        continue
                    else:
                        new_tickets[cid] = data
                if new_tickets:
                    current_tickets[uid] = new_tickets
            await self.config.guild(guild).opened.set(current_tickets)
            if count:
                log.info(f"{count} tickets pruned from {guild.name}")

    # Will automatically close/cleanup any tickets if a member leaves that has an open ticket
    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if not member:
            return
        conf = await self.config.guild(member.guild).all()
        if not conf["auto_close"]:
            return
        opened = conf["opened"]
        if str(member.id) not in opened:
            return
        tickets = opened[str(member.id)]
        if not tickets:
            return
        now = datetime.datetime.now()
        for cid, ticket in tickets.items():
            # Gather data
            pfp = ticket["pfp"]
            opened = ticket["opened"]
            opened = datetime.datetime.fromisoformat(opened)
            opened = opened.strftime('%m/%d/%y at %I:%M %p')
            closed = now.strftime('%m/%d/%y at %I:%M %p')
            embed = discord.Embed(
                title="Ticket Closed",
                description=f"Ticket created by **{member.name}-{member.id}** has been closed.\n"
                            f"`Opened on: `{opened}\n"
                            f"`Closed on: `{closed}\n"
                            f"`Closed by: `{self.bot.user.name}\n"
                            f"`Reason:    `User left guild(Auto-Close)\n",
                color=discord.Color.green()
            )
            embed.set_thumbnail(url=pfp)
            chan = self.bot.get_channel(int(cid))
            if conf["log"]:
                log_chan = self.bot.get_channel(conf["log"])
            else:
                log_chan = None
            # Send off log
            if conf["transcript"]:
                if chan:
                    history = await self.fetch_channel_history(chan)
                    history.reverse()
                    filename = f"{member.name}-{member.id}.txt"
                    filename = filename.replace("/", "")
                    if log_chan:
                        text = ""
                        for msg in history:
                            if msg.author.id == self.bot.user.id:
                                continue
                            if not msg:
                                continue
                            if not msg.content:
                                continue
                            text += f"{msg.author.name}: {msg.content}\n"
                        iofile = StringIO(text)
                        file = discord.File(iofile, filename=filename)
                        await log_chan.send(embed=embed, file=file)
            else:
                if log_chan:
                    await log_chan.send(embed=embed)
            # Delete old log msg
            if log_chan:
                log_msg_id = ticket["logmsg"]
                try:
                    log_msg = await log_chan.fetch_message(log_msg_id)
                except discord.NotFound:
                    log.warning("Failed to get log channel message")
                    log_msg = None
                if log_msg:
                    try:
                        await log_msg.delete()
                    except Exception as e:
                        log.warning(f"Failed to auto-delete log message: {e}")
            # Delete ticket channel
            try:
                await chan.delete()
            except Exception as e:
                log.warning(f"Failed to auto-delete ticket channel: {e}")
        async with self.config.guild(member.guild).opened() as tickets:
            if str(member.id) in tickets:
                del tickets[str(member.id)]
