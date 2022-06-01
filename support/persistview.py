import datetime
import logging
from typing import Union

import discord
from redbot.core import commands, Config

log = logging.getLogger("red.vrt.support.persistview")


class SupportButton(discord.ui.Button, commands.Cog):
    def __init__(self, config, label, style, emoji):
        super().__init__(label=label, style=style, emoji=emoji)
        self.config = config

    async def callback(self, interaction):
        await interaction.response.defer()
        guild = interaction.guild
        user = interaction.user
        await self.create_ticket(guild, user)

    # Create a ticket channel for the user
    async def create_ticket(self, guild: discord.Guild, user: discord.User):

        pfp = user.avatar.url
        conf = await self.config.guild(guild).all()
        if str(user.id) in conf["opened"]:
            tickets = len(conf["opened"][str(user.id)].keys())
            if tickets >= conf["max_tickets"]:
                return
        category = guild.get_channel(conf["category"])
        if not category:
            return
        can_read = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        read_and_manage = discord.PermissionOverwrite(
            read_messages=True, send_messages=True, manage_channels=True, manage_permissions=True
        )
        support = [
            guild.get_role(role_id) for role_id in conf["support"] if guild.get_role(role_id)
        ]
        overwrite = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            guild.me: read_and_manage,
            user: can_read
        }
        for role in support:
            overwrite[role] = can_read
        num = conf["num"]

        now = datetime.datetime.now()
        name_fmt = conf["ticket_name"]
        if name_fmt == "{default}":
            channel_name = f"{user.name}"
        else:
            params = {
                "num": str(num),
                "user": user.name,
                "id": str(user.id),
                "shortdate": now.strftime("%m-%d"),
                "longdate": now.strftime("%m-%d-%Y"),
                "time": now.strftime("%I-%M-%p")
            }
            channel_name = name_fmt.format(**params)
        channel = await category.create_text_channel(channel_name, overwrites=overwrite)
        # Ticket message setup
        embeds = conf["embeds"]
        color = user.color
        if conf["message"] == "{default}":
            if conf["user_can_close"]:
                text = f"Welcome to your ticket channel\nTo close this, " \
                       f"You or an Administrator may run `[p]sclose`."
                if embeds:
                    msg = await channel.send(user.mention, embed=discord.Embed(description=text, color=color))
                else:
                    msg = await channel.send(f"{user.mention}, {text}")
            else:
                text = f"Welcome to your ticket channel"
                if embeds:
                    msg = await channel.send(user.mention, embed=discord.Embed(description=text, color=color))
                else:
                    msg = await channel.send(f"{user.mention}, {text}")
        else:
            try:
                params = {
                    "username": user.name,
                    "mention": user.mention,
                    "id": str(user.id)
                }
                tmessage = conf["message"].format(**params)
                if embeds:
                    if "mention" in conf["message"]:
                        msg = await channel.send(user.mention, embed=discord.Embed(description=tmessage, color=color))
                    else:
                        msg = await channel.send(embed=discord.Embed(description=tmessage, color=color))
                else:
                    msg = await channel.send(tmessage, allowed_mentions=discord.AllowedMentions(users=True, roles=True))
            except Exception as e:
                log.warning(f"An error occurred while sending a ticket message: {e}")
                # Revert to default message
                if conf["user_can_close"]:
                    text = f"Welcome to your ticket channel\nTo close this, " \
                           f"You or an Administrator may run `[p]sclose`."
                    if embeds:
                        msg = await channel.send(user.mention, embed=discord.Embed(description=text, color=color))
                    else:
                        msg = await channel.send(f"{user.mention}, {text}")
                else:
                    text = f"Welcome to your ticket channel"
                    if embeds:
                        msg = await channel.send(user.mention, embed=discord.Embed(description=text, color=color))
                    else:
                        msg = await channel.send(f"{user.mention}, {text}")

        async with self.config.guild(guild).all() as settings:
            settings["num"] += 1
            opened = settings["opened"]
            if str(user.id) not in opened:
                opened[str(user.id)] = {}
            opened[str(user.id)][str(channel.id)] = {
                "opened": now.isoformat(),
                "pfp": str(pfp),
                "logmsg": None
            }
            if conf["log"]:
                log_channel = guild.get_channel(conf["log"])
                if log_channel:
                    embed = discord.Embed(
                        title="Ticket Opened",
                        description=f"Ticket created by **{user.name}-{user.id}** has been opened\n"
                                    f"To view this ticket, **[Click Here]({msg.jump_url})**",
                        color=discord.Color.red()
                    )
                    embed.set_thumbnail(url=pfp)
                    log_msg = await log_channel.send(embed=embed)
                    opened[str(user.id)][str(channel.id)]["logmsg"] = str(log_msg.id)


class PersistentView(discord.ui.View, commands.Cog):
    def __init__(
            self,
            config: Config,
            message: discord.Message,
            label: str,
            style: discord.ButtonStyle,
            emoji: discord.Emoji = None
    ):
        super().__init__(timeout=None)
        self.config = config
        self.message = message
        self.add_item(SupportButton(config, label, style, emoji))

    async def start(self):
        await self.message.edit(view=self)

    async def interaction_check(self, interaction):
        guild = interaction.guild
        user = str(interaction.user.id)
        conf = await self.config.guild(guild).all()
        if user in conf["opened"]:
            tickets = len(conf["opened"][user].keys())
            if tickets >= conf["max_tickets"]:
                await interaction.response.send_message(
                    content="You already have the maximum amount of tickets opened!",
                    ephemeral=True
                )
                return False
        return True


async def start_button(
        config: Config,
        message: discord.Message,
        label: str,
        style: discord.ButtonStyle,
        emoji: discord.Emoji = None
):
    b = PersistentView(config, message, label, style, emoji)
    await b.start()


class TestButton(discord.ui.View):
    def __init__(
            self,
            style: discord.ButtonStyle,
            label: str,
            emoji: Union[discord.Emoji, discord.PartialEmoji, str] = None
    ):
        super().__init__()
        if emoji:
            butt = discord.ui.Button(
                label=label,
                style=style,
                emoji=emoji
            )
        else:
            butt = discord.ui.Button(
                label=label,
                style=style
            )
        self.add_item(butt)
