import discord
from discord.ui import Button, View
from keep_alive import keep_alive
import aiohttp 
import os
import json
import requests
from discord import ui
from bs4 import BeautifulSoup
from discord import app_commands
import asyncio
import math
from discord.ext import commands
from difflib import get_close_matches
import logging
import re
from dotenv import load_dotenv
from typing import List

load_dotenv()

# Get the Discord bot token from the environment variable
TOKEN = os.getenv('DISCORD_TOKEN')

# Set the logging level to WARNING to suppress lower-level logs
logging.basicConfig(level=logging.WARNING)

# Suppress the specific warnings from discord.py
logging.getLogger('discord.gateway').setLevel(logging.ERROR)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='/', intents=intents)
async def main():
    bot = commands.Bot(command_prefix="/", intents=discord.Intents.all())

    # Load the setup function
    await bot

# Create a global aiohttp session that can be used across the bot's lifetime
session = None

# Event handler for bot ready
@bot.event
async def on_ready():
    global session
    session = aiohttp.ClientSession()  # Initialize aiohttp session when bot is ready
    print(f'Logged in as {bot.user}')
    try:
        num = await bot.tree.sync()
        print(f"[+] {len(num)} loaded")
        await bot.change_presence(activity=discord.Game(name="WBStats"))
    except Exception as e:
        print(e)



# Storage setup
STORAGE_FILE = 'storage.json'

def load_player_data():
    """Load player data from storage.json."""
    if os.path.exists(STORAGE_FILE):
        try:
            with open(STORAGE_FILE, 'r') as f:
                data = json.load(f)
                # Convert old format to new format if necessary
                for user_id, value in data.items():
                    if isinstance(value, str):
                        data[user_id] = {"uid": value, "pfp": None}
                
                return data
        except (json.JSONDecodeError, IOError) as e:
            print(f"Error loading storage file: {e}")
    return {}

def save_player_data(data):
    """Save player data to storage.json."""
    try:
        with open(STORAGE_FILE, 'w') as f:
            json.dump(data, f, indent=4)
            
    except IOError as e:
        print(f"Error saving storage file: {e}")

# Load player data at the module level
player_data = load_player_data()

def get_uid(user_id):
    user_data = player_data.get(str(user_id), {})
    if isinstance(user_data, dict):
        return user_data.get("uid"), user_data.get("pfp")
    else:
        return user_data, None  # For backwards compatibility

def set_uid(user_id, uid, pfpimgurlink=None):
    player_data[str(user_id)] = {"uid": uid, "pfp": pfpimgurlink}
    save_player_data(player_data)

def delete_uid(user_id):
    if str(user_id) in player_data:
        del player_data[str(user_id)]
        save_player_data(player_data)

# Function to calculate KD progress
def calculate_kd_progress(kills, deaths):
    current_kd = round(kills / deaths, 1)
    kd_goal = round(current_kd + 0.1, 1)
    req_kills = kills
    while round(req_kills / deaths, 1) < kd_goal:
        req_kills += 1
    kills_needed = req_kills - kills

    kd_avoid = round(current_kd - 0.1, 1)
    req_deaths = deaths
    while round(kills / req_deaths, 1) > kd_avoid:
        req_deaths += 1
    deaths_to_avoid = req_deaths - deaths

    return kd_goal, kills_needed, kd_avoid, deaths_to_avoid

async def fetch_daily_rankings(uid: str):
    try:
        url = f"https://stats.warbrokers.io/players/i/{uid}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                text = await response.text()

        soup = BeautifulSoup(text, 'html.parser')

        daily_rankings = soup.find("div", id="player-details-dailies-content")
        if daily_rankings:
            rankings = []
            ranking_elements = daily_rankings.find_all("div", class_="player-details-daily-circle-container")
            for element in ranking_elements:
                medal = element.find("div", class_="player-details-daily-circle").text.strip()
                title = element.find("div", class_="tooltip-header").text.strip()
                rankings.append(f"{medal} - {title}")

            if rankings:
                rankings_embed = discord.Embed(
                    title="🏆 Daily Rankings",
                    description="\n".join(rankings),
                    color=0x3498db
                )
                return rankings_embed
            else:
                return discord.Embed(
                    title="No Daily Rankings",
                    description="No daily rankings for you today!",
                    color=0x3498db
                )
        else:
            return discord.Embed(
                title="No Daily Rankings",
                description="No daily rankings for you today!",
                color=0x3498db
            )
    except Exception as e:
        print(f"Error in fetch_daily_rankings: {e}")
        return discord.Embed(
            title="Error",
            description="Failed to fetch daily rankings. Please try again later.",
            color=0xFF0000
        )
# Function to fetch player stats and format as an embed
async def fetch_player_stats(ctx: discord.Interaction, uid: str, pfp_link=None):
    responded = False  # Initialize the responded variable at the start
    try:
        url1 = f"https://stats.warbrokers.io/players/i/{uid}"
        response1 = requests.get(url1)
        soup1 = BeautifulSoup(response1.text, 'html.parser')

        general = {}

        if response1.status_code == 200:
            player_data1 = {}

            header_elements = soup1.find_all("div", class_="player-details-number-box-header")
            value_elements = soup1.find_all("div", class_="player-details-number-box-value")

            for header, value in zip(header_elements, value_elements):
                header_text = header.text.strip()
                value_text = value.text.strip()
                player_data1[header_text] = value_text

            player_name_element1 = soup1.find("div", class_="page-header")
            player_name_parts = player_name_element1.get_text(strip=True).split('Lvl')
            player_name = player_name_parts[0].strip()
            player_level = int(player_name_parts[1].strip())

            # Fetch last seen data from the WarBrokers API
            last_seen_url = f"https://wbapi.wbpjs.com/players/getPlayer?uid={uid}"
            last_seen_response = requests.get(last_seen_url)

            if last_seen_response.status_code == 200:
                last_seen_data = last_seen_response.json()
                m00_losses = last_seen_data.get("losses", {}).get("m00", 0)

                # Fetch the player's total wins
                total_wins = int(player_data1.get("Classic Mode Wins", "0").replace(",", ""))

                # Calculate WLR (Wins / Losses) using only "m00" losses
                wlr = total_wins / m00_losses if m00_losses > 0 else 0

                last_seen_timestamp = last_seen_data.get("time")  # Assuming the API returns a 'time' field

                if last_seen_timestamp:
                    last_seen_formatted = f"<t:{int(last_seen_timestamp)}:R>"
                else:
                    last_seen_formatted = "Data not available"
            else:
                last_seen_formatted = "Failed to fetch last seen data"

            url2 = f"https://stats.wbpjs.com/players/{uid}"
            response2 = requests.get(url2)

            if response2.status_code == 200:
                soup2 = BeautifulSoup(response2.text, 'html.parser')
                xp_element = soup2.find('span', string='XP').find_next('span')
                player_exp = xp_element.text.strip() if xp_element else "N/A"

                # XP percent calculation
                if player_level > 23:
                    exp_needed = (250000 + (25000 * (player_level - 23))) - int(player_exp)
                    exp_progress = math.floor(100 * (1 - (exp_needed / 25000)))
                else:
                    levels_exp = {
                        0: 0, 1: 100, 2: 500, 3: 31500, 4: 3000, 5: 5000,
                        6: 11000, 7: 18000, 8: 27000, 9: 37000, 10: 48000,
                        11: 60000, 12: 73000, 13: 87000, 14: 102000, 15: 117000,
                        16: 132000, 17: 147000, 18: 162000, 19: 177000, 20: 192000,
                        21: 207000, 22: 222000, 23: 237000, 24: 250000
                    }
                    exp_needed = levels_exp[player_level + 1] - int(player_exp)
                    exp_progress = math.floor(100 * (1 - (exp_needed / (levels_exp[player_level + 1] - levels_exp[player_level]))))

                kills_elo_element = soup2.find('span', string='Kills Elo').find_next('span').text
                games_elo_element = soup2.find('span', string='Games Elo').find_next('span').text

                kills = int(player_data1.get("Kills", "0").replace(",", ""))
                deaths = int(player_data1.get("Deaths", "0").replace(",", ""))
                current_kd = kills / deaths if deaths > 0 else 0

                classic_wins = player_data1.get("Classic Mode Wins", "N/A")
                br_wins = player_data1.get("Battle Royale Wins", "N/A")
                zombie_br_wins = player_data1.get("Zombie BR Wins", "N/A")

                # Calculate KD goal, kills needed, and deaths to avoid
                kd_goal, kills_needed, kd_avoid, deaths_to_avoid = calculate_kd_progress(kills, deaths)

                try:
                    # Grab all instances of ribbons
                    content = soup1.find_all('div', class_="ribbon-wrapper")
                    ribbon_groups = str(content).split('/images/ribbons/heartStar.png')
                    while len(ribbon_groups) > 2:
                        ribbon_groups.pop(0)
                    ribbon_groups = str(content).split('purpleHeart')
                    ribbons = str(ribbon_groups[0]).split(
                        'style=&quot;background:#454658;&quot;&gt;'
                    ) if len(ribbon_groups) == 3 else str(
                        ribbon_groups[2]).split(
                            'style=&quot;background:#454658;&quot;&gt;')
                    ribbons.pop(0)
                    ribbons.pop(-1)  # we don't need the purple heart ribbon

                    # Define medal emojis
                    medal_emojis = {
                        'Gold': '<:goldStar:1298137739694182440>',
                        'Silver': '<:silverStar:1298137743003488367>',
                        'Bronze': '<:bronzeStar:1298137736083148800>'
                    }

                    # Initialize medals with emoji info
                    medals = {
                        'Gold': {'count': 0, 'emoji': medal_emojis['Gold']},
                        'Silver': {'count': 0, 'emoji': medal_emojis['Silver']},
                        'Bronze': {'count': 0, 'emoji': medal_emojis['Bronze']},
                        'Ribbon': {'count': 0, 'emoji': ''},
                        'Unearned': {'count': 0, 'emoji': ''}
                    }

                    for ribbon in ribbons:
                        name = str(ribbon.split('&')[0])
                        if str(ribbon).count('&amp;#10031;') == 4:
                            medals['Gold']['count'] += 1
                        elif str(ribbon).count('&amp;#10031;') == 3:
                            medals['Silver']['count'] += 1
                        elif str(ribbon).count('&amp;#10031;') == 2:
                            medals['Bronze']['count'] += 1
                        elif str(ribbon).count('&amp;#10031;') == 1:
                            medals['Ribbon']['count'] += 1
                        else:
                            medals['Unearned']['count'] += 1

                    general['Medals'] = medals

                except Exception as e:
                    print(e)
                    general['Medals'] = {
                        'Gold': {'count': 0, 'emoji': medal_emojis['Gold']},
                        'Silver': {'count': 0, 'emoji': medal_emojis['Silver']},
                        'Bronze': {'count': 0, 'emoji': medal_emojis['Bronze']},
                        'Ribbon': {'count': 0, 'emoji': ''},
                        'Unearned': {'count': 0, 'emoji': ''}
                    }

                player_elo = float(kills_elo_element.strip())

                # Rankings defined as tuples (name, ELO, emoji)
                rankings = [
                    ("Bronze", 1500, "<:bronze:1297740711617237064>"),
                    ("Iron", 1600, "<:iron:1297740730101534730>"),
                    ("Silver", 1700, "<:silver:1297740740314529812>"),
                    ("Gold", 1800, "<:gold:1297740724347080785>"),
                    ("Platinum", 1900, "<:platinum:1297740737307344916>"),
                    ("Diamond", 2000, "<:diamond:1297740714821550121>"),
                    ("Elite", 2100, "<:elite:1297740717803962400>"),
                    ("Immortal", 2200, "<:immortal:1297740727433822342>"),
                    ("Mythic", 2300, "<:mythic:1297740733968810064>"),
                    ("Eternal", 2400, "<:eternal:1297740721226252338>")
                ]

                current_rank = None
                next_rank_elo = None
                for rank, elo_threshold, emoji in rankings:
                    if player_elo >= elo_threshold:
                        current_rank = (rank, emoji)
                    else:
                        next_rank_elo = elo_threshold
                        break

                # Create stats embed
                stats_embed = discord.Embed(
                    title=f"🛡️ Stats of {player_name} 🛡️",
                    description="Proud stats of a fearless fighter! 🏹",
                    color=0x2ecc71
                )

                stats_embed.set_thumbnail(url=pfp_link if pfp_link else "https://i.imgur.com/Rt6nDrT.png")

                stats_embed.add_field(name="📜 Stats ID", value=uid, inline=False)

                if current_rank:
                    rank_name, rank_emoji = current_rank
                    elo_needed = (next_rank_elo - player_elo) if next_rank_elo else 0
                    elo_needed_text = f"({elo_needed:.0f} ELO more needed for next rank)" if next_rank_elo else "(Max rank reached)"
                    stats_embed.add_field(name="🎖️ Rank", value=f"{rank_emoji} {rank_name} {elo_needed_text}\n*Use /ranks for more info*", inline=False)

                stats_embed.add_field(name="🔹 Level", value=player_level, inline=True)
                stats_embed.add_field(name="⏳ XP Progress", value=f"{exp_progress}% ({exp_needed} XP to go)\n*Type `/expinfo` for more!*", inline=True)

                # Last Seen Online
                stats_embed.add_field(name="🕐 Last Active", value=last_seen_formatted, inline=True)
                stats_embed.add_field(name="🔫 Kills", value=player_data1.get("Kills", "N/A"), inline=True)
                stats_embed.add_field(name="⚖️ W/L Ratio", value=f"{wlr:.2f}", inline=True)
                stats_embed.add_field(name="⚖️ K/D", value=player_data1.get("Kills / Death", "N/A"), inline=True)
                stats_embed.add_field(name="🏆 Classic Mode Wins", value=classic_wins, inline=True)
                stats_embed.add_field(name="🏆 BR Wins", value=br_wins, inline=True)
                stats_embed.add_field(name="🏆 Zombie BR Wins", value=zombie_br_wins, inline=True)
                stats_embed.add_field(name="🏅 Kills ELO", value=str(int(float(kills_elo_element.strip()))), inline=True)
                stats_embed.add_field(name="🏆 Games ELO", value=str(int(float(games_elo_element.strip()))), inline=True)

                # Add other fields as needed
                stats_embed.add_field(name="\u200B", value="\u200B", inline=True)

                # Create medals display string
                ribbons_str = []
                for medal_type, data in general['Medals'].items():
                    count = data['count']
                    emoji = data['emoji']
                    display_emoji = emoji + ' ' if count > 0 and emoji else ''
                    ribbons_str.append(f"{display_emoji}{medal_type}: {count}")

                stats_embed.add_field(
                    name="🏅 Medals",
                    value="\n".join(ribbons_str),
                    inline=False
                )

                stats_embed.add_field(
                    name="🎯 K/D Goal",
                    value=(
                        f"To boost your K/D to {round(current_kd + 0.1, 1)}, you need **{kills_needed} more kills**! "
                        f"And remember, avoid **{deaths_to_avoid} deaths**"
                    ),
                    inline=False
                )

                if not pfp_link:
                    stats_embed.add_field(
                        name="🖼️ Customize Your Stats",
                        value="Want a custom PFP? Use `/help` to learn how to set yours up!",
                        inline=False
                    )

                # Initialize the view
                view = View()

                main_stats_button = Button(label="Main Stats", url=f"https://stats.warbrokers.io/players/i/{uid}")
                elo_stats_button = Button(label="ELO Stats", url=f"https://stats.wbpjs.com/players/{uid}")
                support_button = Button(label="Support Server", url="https://discord.gg/7BgVryKcCz")
                view.add_item(main_stats_button)
                view.add_item(elo_stats_button)
                view.add_item(support_button)

                daily_rankings_button = Button(label="Daily Rankings", style=discord.ButtonStyle.primary)

                async def daily_rankings_callback(interaction: discord.Interaction):
                    rankings_embed = await fetch_daily_rankings(uid)
                    if rankings_embed:
                        await interaction.response.send_message(embed=rankings_embed, ephemeral=True)
                    else:
                        await interaction.response.send_message("Failed to fetch daily rankings. Please try again later.", ephemeral=True)

                daily_rankings_button.callback = daily_rankings_callback
                view.add_item(daily_rankings_button)

                return stats_embed, view
    except Exception as e:
        print(f"Error in fetch_player_stats: {e}")
        return None, None
@bot.tree.command(
    name='stats',
    description='📊 Unleash your stats and see your epic performance!'
)
async def stats(ctx: discord.Interaction):
    await ctx.response.defer()

    user_id = ctx.user.id
    uid, pfp_link = get_uid(user_id)  # Fetching the UID and PFP link

    if uid:
        stats_embed, view = await fetch_player_stats(ctx, uid, pfp_link)

        if stats_embed:
            # Create a custom view with buttons
            class StatsView(discord.ui.View):
                def __init__(self):
                    super().__init__(timeout=None)
                    self.add_item(discord.ui.Button(label="Main Stats", url=f"https://stats.warbrokers.io/players/i/{uid}"))
                    self.add_item(discord.ui.Button(label="ELO Stats", url=f"https://stats.wbpjs.com/players/{uid}"))
                    self.add_item(discord.ui.Button(label="Support Server", url="https://discord.gg/7BgVryKcCz"))

                @discord.ui.button(label="Daily Rankings", style=discord.ButtonStyle.primary)
                async def toggle_rankings(self, interaction: discord.Interaction, button: discord.ui.Button):
                    if button.label == "Daily Rankings":
                        rankings_embed = await fetch_daily_rankings(uid)
                        button.label = "Back to Stats"
                        await interaction.response.edit_message(embed=rankings_embed, view=self)
                    else:
                        button.label = "Daily Rankings"
                        await interaction.response.edit_message(embed=stats_embed, view=self)

            custom_view = StatsView()
            await ctx.followup.send(embed=stats_embed, view=custom_view)
        else:
            await ctx.followup.send("⚠️ You entered your UID wrong. Please check and try again using the /linkstats command!")
    else:
        error_embed = discord.Embed(
            title="Stats Not Found 😅",
            description="It looks like your stats aren't linked yet. No worries, just use `/linkstats` to set it up and get back to the action!",
            color=0xFF0000
        )
        error_embed.set_thumbnail(url="https://i.imgur.com/Rt6nDrT.png")
        error_embed.set_image(url="https://i.imgur.com/NRPp0DP.png")
        error_embed.set_footer(text="WBStats | Inspired by SquadBot and POMP's Mod")
        await ctx.followup.send(embed=error_embed)
@bot.tree.command(
    name='linkstats',
    description='🔗 Link your stats and save the hassle. Easy peasy!'
)
async def linkstats(ctx: discord.Interaction, id: str, pfpimgurlink: str = None):
    user_id = ctx.user.id

    # Regular expression to validate Imgur URLs
    imgur_url_pattern = r"^(https?://)?(www\.)?(imgur\.com|i\.imgur\.com)/.+\.(jpg|jpeg|png|gif)$"

    # Validate the Imgur link if provided
    if pfpimgurlink and not re.match(imgur_url_pattern, pfpimgurlink):
        # If the link is invalid, notify the user and fallback to default PFP
        response = (f"⚠️ The provided image link is invalid. Your profile picture will be set to default. "
                    f"Your link should look like this: ``https://i.imgur.com/Am7ublS.png``")
        pfpimgurlink = None  # Set to None to indicate no valid PFP
    else:
        response = ""

    # Call the function to set the user ID and profile picture
    set_uid(user_id, id, pfpimgurlink)

    # Construct the response message
    response += f"🚀 Stats ID linked for {ctx.user.mention}! 🎯 Now you're all set to use `/stats` and show off your epicness."
    if pfpimgurlink:
        response += "\n🖼️ Custom profile picture has been set!"
    else:
        response += "\n⚠️ No custom profile picture set. You can add one later using this command again!"

    await ctx.response.send_message(content=response, ephemeral=True)

@bot.tree.command(
    name='statsof',
    description='Peek into another player\'s stats with their ID!'
)
async def statsof(ctx: discord.Interaction, uid: str):
    await ctx.response.defer()

    # Fetch stats without sending a message directly inside the function
    stats_embed, view = await fetch_player_stats(ctx, uid)

    if stats_embed:
        # Set the default thumbnail for the statsof command
        stats_embed.set_thumbnail(url="https://i.imgur.com/Rt6nDrT.png")

        # Send the embed with the view
        await ctx.followup.send(embed=stats_embed, view=view)
    else:
        await ctx.followup.send("Failed to retrieve player stats. Please try again later.")


# Help command showing all available commands
class CustomPFPButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.primary, label="Custom PFP")

    async def callback(self, interaction: discord.Interaction):
        try:
            custom_pfp_embed = discord.Embed(
                title="🖼️ Setting Up Your Custom Profile Picture",
                description="Follow these steps to set up your custom profile picture using Imgur:",
                color=0x3498db
            )
            custom_pfp_embed.add_field(
                name="Step 1: Upload Your Image",
                value="Upload your desired profile picture to [Imgur](https://imgur.com/upload).",
                inline=False
            )
            custom_pfp_embed.add_field(
                name="Step 2: Get the Image Link",
                value="After uploading, right-click on the image and select 'Copy image address'.",
                inline=False
            )
            custom_pfp_embed.add_field(
                name="Step 3: Link Your Stats with Custom PFP",
                value="Use the `/linkstats` command with your War Brokers ID and the Imgur link:\n`/linkstats id: pfpimgurlink:`",
                inline=False
            )
            custom_pfp_embed.add_field(
                name="Example",
                value="`/linkstats id:123456 pfpimgurlink:https://i.imgur.com/abcdefg.png`",
                inline=False
            )
            custom_pfp_embed.set_footer(text="Note: Make sure to use a direct image link from Imgur (ending with .jpg, .png, etc.)")

            # Create a view with the HelpButton to return to the help embed
            view = discord.ui.View()
            view.add_item(HelpButton())  # Add the HelpButton to the view

            await interaction.response.edit_message(embed=custom_pfp_embed, view=view)
        except Exception as e:
            print(f"Error in CustomPFPButton callback: {e}")
            await interaction.response.send_message("Something went wrong while setting up your custom PFP. Please try again.", ephemeral=True)


class HelpButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.secondary, label="Back to Help")

    async def callback(self, interaction: discord.Interaction):
        try:
            help_embed = discord.Embed(
                title="💡 Help Command Center! 💡",
                description="Check out these epic commands you can unleash in the game! 🚀",
                color=0x3498db
            )
            help_embed.set_thumbnail(url="https://i.imgur.com/Rt6nDrT.png")

            commands = [
                {
                    "name": "/stats",
                    "description": "🛡️ Show your stats",
                    "details": "Want to flex your stats? This command's got your back! Plus, you can now check your daily rankings."
                },
                {
                    "name": "/linkstats",
                    "description": "🔗 Link your stats",
                    "details": "Tired of typing your ID every time? Link your stats and save the hassle!"
                },
                {
                    "name": "/statsof",
                    "description": "📜 Show stats of any player",
                    "details": "Curious about another player? Enter their stats ID and check them out!"
                },
                {
                    "name": "/expinfo",
                    "description": "📈 XP Breakdown",
                    "details": "Ever wondered how to get that next level up? This command breaks it down for you!"
                },
                {
                    "name": "/squad",
                    "description": "📊 Squad Stats",
                    "details": "Get the average Kills ELO, Games ELO, and game mode wins for your squad."
                },
                {
                    "name": "/findmatch",
                    "description": "🔍 Find Matches",
                    "details": "Looking for a match? This command will list active servers with game modes, maps, and player counts."
                },
                {
                    "name": "/weapon",
                    "description": "🔫 View Weapons",
                    "details": "Explore different weapon categories."
                },
                {
                    "name": "/vehicle",
                    "description": "🚗 View Vehicle Information",
                    "details": "Discover vehicle categories, check damage values, and **see which maps each vehicle is available on**!"
                },
                {
                    "name": "/ranks",
                    "description": "🏆 View Ranks",
                    "details": "See all the available ranks based on your Kills ELO, and check what rank you are in the game!"
                }
            ]



            for command in commands:
                help_embed.add_field(
                    name=command["name"],
                    value=f"{command['description']}\n{command['details']}",
                    inline=False
                )

            help_embed.set_footer(text="WBStats | Inspired by SquadBot and POMP's Mod")

            # Create the view with buttons for CustomPFPButton and the Support Server link
            view = discord.ui.View()
            view.add_item(CustomPFPButton())
            view.add_item(discord.ui.Button(label="Support Server", url="https://discord.com/invite/WehCXEJGCQ"))

            await interaction.response.edit_message(embed=help_embed, view=view)
        except Exception as e:
            print(f"Error in HelpButton callback: {e}")
            await interaction.response.send_message("Something went wrong while returning to help. Please try again.", ephemeral=True)


@bot.tree.command(
    name='help',
    description='🆘 Need a hand? Get the scoop on all the commands you can use!'
)
async def help_command(ctx: discord.Interaction):
    await ctx.response.defer()  # Defer the response to prevent the command from timing out

    embed = discord.Embed(
        title="💡 Help Command Center! 💡",
        description="Check out these epic commands you can unleash in the game! 🚀",
        color=0x3498db
    )
    embed.set_thumbnail(url="https://i.imgur.com/Rt6nDrT.png")

    commands = [
        {
            "name": "/stats",
            "description": "🛡️ Show your stats",
            "details": "Want to flex your stats? This command's got your back! Plus, you can now check your daily rankings."
        },
        {
            "name": "/linkstats",
            "description": "🔗 Link your stats",
            "details": "Tired of typing your ID every time? Link your stats and save the hassle!"
        },
        {
            "name": "/statsof",
            "description": "📜 Show stats of any player",
            "details": "Curious about another player? Enter their stats ID and check them out!"
        },
        {
            "name": "/expinfo",
            "description": "📈 XP Breakdown",
            "details": "Ever wondered how to get that next level up? This command breaks it down for you!"
        },
        {
            "name": "/squad",
            "description": "📊 Squad Stats",
            "details": "Get the average Kills ELO, Games ELO, and game mode wins for your squad."
        },
        {
            "name": "/findmatch",
            "description": "🔍 Find Matches",
            "details": "Looking for a match? This command will list active servers with game modes, maps, and player counts."
        },
        {
            "name": "/weapon",
            "description": "🔫 View Weapons",
            "details": "Explore different weapon categories."
        },
        {
            "name": "/vehicle",
            "description": "🚗 View Vehicle Information",
            "details": "Discover vehicle categories, check damage values, and **see which maps each vehicle is available on**!"
        },
        {
            "name": "/ranks",
            "description": "🏆 View Ranks",
            "details": "See all the available ranks based on your Kills ELO, and check what rank you are in the game!"
        }
    ]



    for command in commands:
        embed.add_field(
            name=command["name"],
            value=f"{command['description']}\n{command['details']}",
            inline=False
        )

    embed.set_footer(text="WBStats | Inspired by SquadBot and POMP's Mod")

    # Create the view with the CustomPFPButton and HelpButton
    view = discord.ui.View()
    view.add_item(CustomPFPButton())
    view.add_item(discord.ui.Button(label="Support Server", url="https://discord.gg/7BgVryKcCz"))

    # Send the embed with the interactive buttons
    await ctx.followup.send(embed=embed, view=view)
@bot.tree.command(name='expinfo',
                  description='Show how to rack up some sweet XP')
async def expinfo(ctx: discord.Interaction):
    embed = discord.Embed(
        title="Experience Points Guide",
        description="Here's how to earn XP effectively:",
        color=0xF39C12)
    embed.set_thumbnail(url="https://i.imgur.com/Rt6nDrT.png")

    embed.add_field(name="20 XP",
                    value="Assist a teammate.",
                    inline=True)
    embed.add_field(name="40 XP",
                    value="Eliminate an enemy.",
                    inline=True)
    embed.add_field(name="60 XP",
                    value="Achieve a 2 Kill Streak.",
                    inline=True)
    embed.add_field(name="80 XP",
                    value="Achieve a 3 Kill Streak.",
                    inline=True)
    embed.add_field(name="100 XP",
                    value="Achieve a 4 Kill Streak.",
                    inline=True)
    embed.add_field(name="120 XP",
                    value="Achieve a 5 Kill Streak.",
                    inline=True)
    embed.add_field(name="140 XP",
                    value="Achieve a 6 Kill Streak.",
                    inline=True)
    embed.add_field(name="160 XP",
                    value="Achieve a 7 Kill Streak.",
                    inline=True)
    embed.add_field(name="180 XP",
                    value="Achieve an 8 Kill Streak.",
                    inline=True)
    embed.add_field(name="200 XP",
                    value="Achieve 9 or more Kill Streaks.",
                    inline=True)

    embed.add_field(name="50 XP",
                    value="Complete an objective.",
                    inline=True)
    embed.add_field(name="50 XP",
                    value="Complete a mission.",
                    inline=True)
    embed.add_field(name="5 XP",
                    value="Survive for 25 seconds.",
                    inline=True)
    embed.add_field(name="80 XP",
                    value="Finish as the top player on the leaderboard.",
                    inline=True)
    embed.add_field(name="300 XP",
                    value="Receive a consolation prize for losing.",
                    inline=True)
    embed.add_field(name="500 XP",
                    value="Win the match.",
                    inline=True)

    view = View()

    support_button = Button(
        label="Support Server",
        url="https://discord.com/invite/WehCXEJGCQ"
    )


    view.add_item(support_button)


    embed.set_footer(text="WBStats | Inspired by SquadBot and POMP's Mod")

    await ctx.response.send_message(embed=embed)
@bot.tree.command(name='squad', description='📊 Get the average Kills ELO and Games ELO of a squad along with game mode wins.')
async def squad(ctx: discord.Interaction, tag: str):
    try:
        # Create an embed for the loading message
        loading_embed = discord.Embed(
            description="Hold tight! I'm digging up your stats right now... This might take around **38 to 60 seconds**.\nNeed a hand? Use `/help` for assistance.",
            color=0x3498db
        )
        loading_embed.set_image(url="https://i.imgur.com/wu7kNPr.gif")

        # Send the embed instead of a plain message
        await ctx.response.send_message(embed=loading_embed, ephemeral=True)

        async with aiohttp.ClientSession() as session:
            # Fetch squad data from the API
            api_url = f"https://wbapi.wbpjs.com/squad/getSquadMembers?squadName={tag}"
            async with session.get(api_url) as api_response:
                if api_response.status == 200:
                    squad_members = await api_response.json()

                    if not squad_members:
                        await ctx.followup.send(f"No stats found for squad tag `{tag}`. Please note that squad tags are case-sensitive. Try again!", ephemeral=True)
                        return

                    # Initialize accumulators
                    total_kills = 0
                    total_deaths = 0
                    total_kills_elo = 0
                    total_games_elo = 0
                    total_level = 0
                    count = len(squad_members)

                    # Concurrently fetch player stats using asyncio.gather
                    async def fetch_player_stats(uid):
                        player_url = f"https://stats.warbrokers.io/players/i/{uid}"
                        async with session.get(player_url) as player_response:
                            if player_response.status == 200:
                                player_soup = BeautifulSoup(await player_response.text(), 'html.parser')
                                player_data = {}

                                # Extract data based on headers and values
                                header_elements = player_soup.find_all("div", class_="player-details-number-box-header")
                                value_elements = player_soup.find_all("div", class_="player-details-number-box-value")

                                for header, value in zip(header_elements, value_elements):
                                    header_text = header.text.strip()
                                    value_text = value.text.strip().replace(',', '')  # Remove commas from numbers

                                    # Handle Kills and Deaths as integers, and K/D as a float
                                    
                                    if header_text in ['Kills', 'Deaths']:
                                        player_data[header_text] = int(value_text)  # Convert to int
                                    elif header_text == 'Kills / Death':  # Handle K/D ratio
                                        player_data[header_text] = float(value_text)  # Convert to float

                                # Return kills and deaths
                                return player_data.get('Kills', 0), player_data.get('Deaths', 0)
                            else:
                                return 0, 0

                    # Fetch all player stats concurrently
                    tasks = [fetch_player_stats(member.get("uid")) for member in squad_members]
                    player_stats = await asyncio.gather(*tasks)

                    # Process player stats
                    for (kills, deaths), member in zip(player_stats, squad_members):
                        total_kills_elo += member.get("killsELO", 0)
                        total_games_elo += member.get("gamesELO", 0)
                        total_level += member.get("level", 0)
                        total_kills += kills
                        total_deaths += deaths

                    # Calculate average ELOs and KD ratio
                    avg_kills_elo = total_kills_elo / count
                    avg_games_elo = total_games_elo / count
                    overall_kd = total_kills / total_deaths if total_deaths > 0 else 0

                    # Fetch game mode wins from HTML
                    html_url = f"https://stats.warbrokers.io/squads/{tag}"
                    async with session.get(html_url) as html_response:
                        if html_response.status == 200:
                            soup = BeautifulSoup(await html_response.text(), 'html.parser')

                            # Extract stats from HTML
                            game_wins = {
                                "Death Match": soup.find('div', string=lambda text: text and 'Death Match' in text).find_next_sibling('div').string.strip(),
                                "Battle Royale": soup.find('div', string=lambda text: text and 'Battle Royale' in text).find_next_sibling('div').string.strip(),
                                "Missile Launch": soup.find('div', string=lambda text: text and 'Missile Launch' in text).find_next_sibling('div').string.strip(),
                                "Vehicle Escort": soup.find('div', string=lambda text: text and 'Vehicle Escort' in text).find_next_sibling('div').string.strip(),
                                "Capture Point": soup.find('div', string=lambda text: text and 'Capture Point' in text).find_next_sibling('div').string.strip(),
                                "Package Drop": soup.find('div', string=lambda text: text and 'Package Drop' in text).find_next_sibling('div').string.strip(),
                                "Zombie BR": soup.find('div', string=lambda text: text and 'Zombie BR' in text).find_next_sibling('div').string.strip()
                            }

                            # Create the embed
                            num_members = count  # Number of members in the squad

                            squad_embed = discord.Embed(
                                title=f"🏆 Squad Stats for {tag} 🏆",
                                description="Here's a detailed look at the squad stats.",
                                color=0x3498db
                            )
                            squad_embed.add_field(name="Squad Members", value=f"{num_members}", inline=True)
                            squad_embed.add_field(name="Squad Level", value=f"{total_level}", inline=True)
                            squad_embed.add_field(name="\u200B",
                                  value="\u200B",
                                  inline=True)
                            squad_embed.add_field(name="Total Squad Kills", value=f"{total_kills:,}", inline=True)
                            squad_embed.add_field(name="Total Squad Deaths", value=f"{total_deaths:,}", inline=True)
                            squad_embed.add_field(name="Overall Squad KD", value=f"{overall_kd:.2f}", inline=True)
                            squad_embed.add_field(name="Average Kills ELO", value=f"{avg_kills_elo:.2f}", inline=True)
                            squad_embed.add_field(name="Average Games ELO", value=f"{avg_games_elo:.2f}", inline=True)
                            squad_embed.set_thumbnail(
                                url="https://i.imgur.com/Rt6nDrT.png")

                            squad_embed.set_footer(text="WBStats | Inspired by SquadBot and POMP's Mod")




                            # Add game mode wins
                            for mode, wins in game_wins.items():
                                squad_embed.add_field(name=f"{mode} Wins", value=wins, inline=False)

                            view = View()

                            squad_stats = Button(
                                label=f"{tag}",
                                url=f"https://stats.warbrokers.io/squads/{tag}"
                            )
                            view.add_item(squad_stats)

                            support_button = Button(
                                label="Support Server",
                                url="https://discord.gg/7BgVryKcCz"
                            )
                            view.add_item(support_button)

                            # Send the message with embed
                            await ctx.followup.send(embed=squad_embed, view=view)  

                        else:
                            await ctx.followup.send("Failed to retrieve game mode wins from the HTML page.", ephemeral=True)

                else:
                    await ctx.followup.send("No stats found. Please note that squad tags are case-sensitive. Try again!", ephemeral=True)

    except discord.errors.HTTPException as e:
        if e.status == 429:
            await asyncio.sleep(10)  # Wait for 10 seconds before retrying
            await squad(ctx, tag)  # Retry the command
        else:
            print(f"HTTPException: {e}")
            await ctx.followup.send("Something went wrong while fetching squad data.", ephemeral=True)
    except Exception as e:
        print(f"Unexpected error: {e}")
        await ctx.followup.send("Unexpected error occur, Try again later after few minutes", ephemeral=True)


Modes = {
    "tdm": 128, "ml": 138, "bd": 275, "cp": 135, "ve": 136, "gg": 15,
}
Modes_long = {
    "Team Death Match": 128, "Missile Launch": 138, "Bomb Disposal": 275,
    "Capture Points": 135, "Vehicle Escort": 136, "Gun Game": 15,
}
Maps = {
    "area15base": 21, "area15bunker": 22, "citypoint": 13, "cologne": 44,
    "desert": 0, "escape": 6, "flooded": 4, "frontier": 31, "goldmine": 47,
    "heist": 32, "kitchen": 29, "moonbase": 20, "northwest": 1, "office": 3,
    "pacific": 2, "remagen": 8, "siege": 39, "skullisland": 24, "southwest": 7,
    "spacestation": 38, "temple": 5, "thesomme": 15, "tomb": 14, "tribute": 18,
    "tribute(cyberpunk)": 19, "cyberpunk": 19, "zengarden": 43, "containers": 37,
    "crisscross": 40, "dwarfsdungeon": 28, "dwarf'sdungeon": 28, "dwarfdungeon": 28,
    "hanger": 25, "pyramid": 36, "quarry": 27, "sniperalley": 35, "snipersonly": 41,
    "threelane": 34, "towerofpower": 33,
}

classic = ["USA", "USA_WEST", "ASIA", "JAPAN", "EUROPE", "INDIA", "AUSTRALIA", "RUSSIA"]
fourvfour = ["USA_4V4", "EU_4V4", "ASIA_4V4"]

@bot.tree.command(
    name='findmatch',
    description='🔍 Find a War Brokers match that suits your preferences!'
)
@app_commands.choices(game=[
    app_commands.Choice(name="Classic", value="classic"),
    app_commands.Choice(name="4v4", value="4v4")
])
@app_commands.choices(player_comparison=[
    app_commands.Choice(name="Greater than or equal to", value="G"),
    app_commands.Choice(name="Less than or equal to", value="L")
])
async def findmatch(
    ctx: discord.Interaction,
    game: app_commands.Choice[str],
    player_comparison: app_commands.Choice[str],
    player_count: int,
    mode: str = None,
    map: str = None,
    region: str = None
):
    await ctx.response.defer()

    settings = set_data(game.value, [player_comparison.value == "G", player_count], mode, map, region)
    matches = await game_check(settings)

    embed = discord.Embed(title="🎮 War Brokers Match Finder", color=0x3498db)
    embed.add_field(name="🏆 Game", value=game.name, inline=True)
    embed.add_field(name="👥 Players", value=f"{'≥' if player_comparison.value == 'G' else '≤'}{player_count}", inline=True)
    embed.add_field(name="🎯 Mode", value=mode.upper() if mode else "Any", inline=True)
    embed.add_field(name="🗺️ Map", value=map.capitalize() if map else "Any", inline=True)
    embed.add_field(name="🌍 Region", value=region.upper() if region else "Any", inline=True)

    if matches:
        embed.description = f"Found {len(matches)} match{'es' if len(matches) > 1 else ''}! 🎉"
        for match in matches[:5]:  # Limit to 5 matches to avoid hitting Discord's embed limits
            embed.add_field(name=f"Match in {match['location']} 📍", 
                            value=f"Mode: {match['mode']}\nMap: {match['map']}\nPlayers: {match['players']}/16", 
                            inline=False)
        if len(matches) > 5:
            embed.set_footer(text=f"Showing 5 out of {len(matches)} matches.")
    else:
        embed.description = "No matches found. 😔 Try adjusting your search criteria!"

    embed.set_thumbnail(url="https://i.imgur.com/Rt6nDrT.png")  # Replace with War Brokers logo URL
    embed.set_footer(text=f"Credits to https://paperblock01.github.io/War-Brokers-Mapper-for-Browser/")

    await ctx.followup.send(embed=embed)

def set_data(game, players, mode, map, location):
    data = [game.lower(), players]

    if mode:
        data.append([Modes[mode.lower()]] if mode.lower() in Modes else "all")
    else:
        data.append("all")

    if map:
        data.append([Maps[map.lower()]] if map.lower() in Maps else "all")
    else:
        data.append("all")

    if location:
        game_regions = classic if game.lower() == "classic" else fourvfour
        data.append([location.upper()] if location.upper() in game_regions else game_regions)
    else:
        data.append(classic if game.lower() == "classic" else fourvfour)

    return data

async def get_server_data(region):
    async with aiohttp.ClientSession() as session:
        async with session.get(f'https://store2.warbrokers.io/293//server_list.php?location={region}') as response:
            text = await response.text()
            return text.split(f",{region},")

async def game_check(set_data):
    matches = []
    for region in set_data[4]:
        server_data = await get_server_data(region)
        for i, server in enumerate(server_data[1:], 1):
            data = server.split(",")
            if check_server(set_data, data):
                matches.append({
                    'location': region,
                    'mode': get_mode_name(int(data[1])),
                    'map': get_map_name(int(data[3])),
                    'players': int(data[2])
                })
    return matches

def check_server(set_data, server_data):
    players = int(server_data[2])
    mode = int(server_data[1])
    map = int(server_data[3])

    if players == 0:
        return False

    if set_data[1][0] and players < set_data[1][1]:
        return False
    if not set_data[1][0] and players > set_data[1][1]:
        return False

    if set_data[2] != "all" and mode not in set_data[2]:
        return False

    if set_data[3] != "all" and map not in set_data[3]:
        return False

    return True

def get_mode_name(mode_id):
    return next((name for name, id in Modes_long.items() if id == mode_id), "Unknown")

def get_map_name(map_id):
    return next((name for name, id in Maps.items() if id == map_id), "Unknown").capitalize()

# Weapon categories and images
WEAPON_CATEGORIES = {
    "Main": [  # Main weapons with 🔫 emoji
        "AK", "AR", "SCAR", "Sniper", ".50 cal", "Hunting", "Auto Sniper", "VSS", "LMG",
        "AKSMG", "SMG", "VEK", "Shotgun", "Tactical Shotgun", "Minigun", "Crossbow",
        "Homing Missile", "RPG", "GL"
    ],
    "Sidearms": [  # Sidearms with 🔫 emoji
        "Pistol", "Auto Pistol", "Deagle", "Revolver", "Healing Pistol"
    ],
    "Melees": [  # Melees with ⚔️ emoji
        "Fists", "Knife", "Rubber Chicken", "Chainsaw"
    ],
    "Deployables": [  # Deployables with 💣 emoji
        "Grenade", "Smoke Grenade", "Implosion Grenade", "Concussion Grenade", "Laser Trip Mine"
    ]
}

# Define a mapping for emojis by category
CATEGORY_EMOJIS = {
    "Main": "🔫",
    "Sidearms": "🔫",
    "Melees": "⚔️",
    "Deployables": "💣"
}

WEAPON_IMAGES = {
    "AK": "https://i.imgur.com/hW0HBUf.png",
    "AR": "https://i.imgur.com/ikGLYj5.png",
    "SCAR": "https://i.imgur.com/Q7dMWBt.png",
    "Sniper": "https://i.imgur.com/ozRyAnX.png",
    ".50 cal": "https://i.imgur.com/nbCes1f.png",
    "Hunting": "https://i.imgur.com/jq4VaZN.png",
    "Auto Sniper": "https://i.imgur.com/GX4rFJI.png",
    "VSS": "https://i.imgur.com/WlABCkY.png",
    "LMG": "https://i.imgur.com/3egOhOE.png",
    "AKSMG": "https://i.imgur.com/OXY5o1s.png",
    "SMG": "https://i.imgur.com/NvgADXM.png",
    "VEK": "https://i.imgur.com/Q4QCNlW.png",
    "Shotgun": "https://i.imgur.com/dONUPTI.png",
    "Tactical Shotgun": "https://i.imgur.com/BOeVM1w.png",
    "Minigun": "https://i.imgur.com/mbJeEaY.png",
    "Crossbow": "https://i.imgur.com/amLXVG3.png",
    "Homing Missile": "https://i.imgur.com/Foaafay.png",
    "RPG": "https://i.imgur.com/f4cDXum.png",
    "GL": "https://i.imgur.com/GMEgqjC.png",
    "Pistol": "https://i.imgur.com/a4h1E7s.png",
    "Auto Pistol": "https://i.imgur.com/m2PN864.png",
    "Deagle": "https://i.imgur.com/7UR5WjU.png",
    "Revolver": "https://i.imgur.com/yQMHbMP.png",
    "Healing Pistol": "https://i.imgur.com/tUqvwo7.png",
    "Fists": "https://i.imgur.com/O4ZzvST.png",
    "Knife": "https://i.imgur.com/F6kfdjf.png",
    "Rubber Chicken": "https://i.imgur.com/tVjAiPo.png",
    "Chainsaw": "https://i.imgur.com/DyqeYbm.png",
    "Grenade": "https://i.imgur.com/vIyQ18p.png",
    "Smoke Grenade": "https://i.imgur.com/jnb8gFC.png",
    "Implosion Grenade": "https://i.imgur.com/iipcDDC.png",
    "Concussion Grenade": "https://i.imgur.com/lxqU40A.png",
    "Laser Trip Mine": "https://i.imgur.com/vEh3ep8.png"
}

WEAPON_WIKI_LINKS = {
    "AK": "https://war-brokers.fandom.com/wiki/AK_Rifle",
    "AR": "https://war-brokers.fandom.com/wiki/AR_Rifle",
    "SCAR": "https://war-brokers.fandom.com/wiki/SCAR",
    "Sniper": "https://war-brokers.fandom.com/wiki/Sniper_Rifle",
    ".50 cal": "https://war-brokers.fandom.com/wiki/.50_Cal_Sniper",
    "Hunting": "https://war-brokers.fandom.com/wiki/Hunting_Rifle",
    "Auto Sniper": "https://war-brokers.fandom.com/wiki/Auto_Sniper",
    "VSS": "https://war-brokers.fandom.com/wiki/VSS",
    "LMG": "https://war-brokers.fandom.com/wiki/LMG",
    "AKSMG": "https://war-brokers.fandom.com/wiki/AK_SMG",
    "SMG": "https://war-brokers.fandom.com/wiki/Sub-Machine_Gun",
    "VEK": "https://war-brokers.fandom.com/wiki/VEK_SMG",
    "Shotgun": "https://war-brokers.fandom.com/wiki/Shotgun",
    "Tactical Shotgun": "https://war-brokers.fandom.com/wiki/Tactical_Shotgun",
    "Minigun": "https://war-brokers.fandom.com/wiki/Minigun",
    "Crossbow": "https://war-brokers.fandom.com/wiki/Crossbow",
    "Homing Missile": "https://war-brokers.fandom.com/wiki/Homing_Missile",
    "RPG": "https://war-brokers.fandom.com/wiki/RPG",
    "GL": "https://war-brokers.fandom.com/wiki/Grenade_Launcher",
    "Pistol": "https://war-brokers.fandom.com/wiki/Pistol",
    "Auto Pistol": "https://war-brokers.fandom.com/wiki/Auto_Pistol",
    "Deagle": "https://war-brokers.fandom.com/wiki/Desert_(weapon)",
    "Revolver": "https://war-brokers.fandom.com/wiki/Revolver",
    "Healing Pistol": "https://war-brokers.fandom.com/wiki/Healing_Pistol",
    "Fists": "https://war-brokers.fandom.com/wiki/Fists",
    "Knife": "https://war-brokers.fandom.com/wiki/Knife",
    "Rubber Chicken": "https://war-brokers.fandom.com/wiki/Rubber_Chicken",
    "Chainsaw": "https://war-brokers.fandom.com/wiki/Chainsaw",
    "Grenade": "https://war-brokers.fandom.com/wiki/Grenade",
    "Smoke Grenade": "https://war-brokers.fandom.com/wiki/Smoke_Grenade",
    "Implosion Grenade": "https://war-brokers.fandom.com/wiki/Implosion_Grenade",
    "Concussion Grenade": "https://war-brokers.fandom.com/wiki/Concussion_Grenade",
    "Laser Trip Mine": "https://war-brokers.fandom.com/wiki/Laser_Trip_Mine"
}

class WeaponInfoView(discord.ui.View):
    def __init__(self, weapons: List[str], category: str, emoji: str):
        super().__init__(timeout=None)
        self.weapons = weapons
        self.category = category
        self.emoji = emoji
        self.current_page = 0
        self.items_per_page = 15  # Number of items per page
        self.update_buttons()

    def create_embed(self):
        start = self.current_page * self.items_per_page
        end = start + self.items_per_page
        current_weapons = self.weapons[start:end]

        embed = discord.Embed(title=f"{self.category} Weapons", color=discord.Color.blue())

        # Create a list of weapons, each prefixed by the emoji
        weapon_list = "\n".join([f"{self.emoji} {weapon}" for weapon in current_weapons])

        # Add the weapon list to the embed
        embed.add_field(name=f"{self.category} Weapons", value=weapon_list, inline=False)

        embed.set_footer(text=f"Page {self.current_page + 1}/{(len(self.weapons) - 1) // self.items_per_page + 1}")
        return embed

    def update_buttons(self):
        self.clear_items()
        for weapon in self.weapons[self.current_page * self.items_per_page:(self.current_page + 1) * self.items_per_page]:
            self.add_item(discord.ui.Button(label=weapon, style=discord.ButtonStyle.primary, custom_id=f"weapon_{weapon}"))

        # Add previous/next buttons for pagination
        if self.current_page > 0:
            self.add_item(discord.ui.Button(label="Previous", style=discord.ButtonStyle.secondary, custom_id="prev_page"))
        if (self.current_page + 1) * self.items_per_page < len(self.weapons):
            self.add_item(discord.ui.Button(label="Next", style=discord.ButtonStyle.secondary, custom_id="next_page"))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        custom_id = interaction.data["custom_id"]
        if custom_id == "prev_page":
            self.current_page -= 1
        elif custom_id == "next_page":
            self.current_page += 1
        elif custom_id.startswith("weapon_"):
            weapon = custom_id[7:]
            weapon_embed = discord.Embed(title=weapon, color=discord.Color.green())
            weapon_embed.set_image(url=WEAPON_IMAGES.get(weapon, ""))
            weapon_embed.set_footer(text="📄 For the latest updates, visit the War Brokers Wiki.")

            # Link to the weapon's wiki page
            wiki_link = WEAPON_WIKI_LINKS.get(weapon, "")
            back_view = discord.ui.View(timeout=None)
            if wiki_link:
                back_view.add_item(discord.ui.Button(label="View on Wiki", url=wiki_link, style=discord.ButtonStyle.link))
            back_view.add_item(discord.ui.Button(label="Back to All Weapons", style=discord.ButtonStyle.secondary, custom_id="back_weapons"))
            
            # Display the selected weapon's embed
            await interaction.response.edit_message(embed=weapon_embed, view=back_view)
            return False

        # Update pagination buttons and reload the weapon list
        self.update_buttons()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)
        return True

    # Function to handle the 'Back to All Weapons' button
    @discord.ui.button(label="Back to All Weapons", style=discord.ButtonStyle.secondary, custom_id="back_weapons")
    async def back_weapons_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Reset the view to show all weapons again
        await interaction.response.edit_message(embed=self.create_embed(), view=self)


# Helper function to show weapon categories
async def show_weapon_categories(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🔫 Weapon Categories", 
        description="Select a category below to view the available weapons.",
        color=discord.Color.blue()
    )

    # Loop through categories and add fields to the embed
    for category, weapons in WEAPON_CATEGORIES.items():
        emoji = CATEGORY_EMOJIS.get(category, "")
        embed.add_field(name=f"{emoji} {category}", value=f"View {category} weapons", inline=False)

    embed.set_footer(text="📄 For the latest updates, visit the War Brokers Wiki.")
    embed.set_thumbnail(url="https://i.imgur.com/Rt6nDrT.png")

    # Create buttons for each weapon category
    view = discord.ui.View(timeout=None)
    for category in WEAPON_CATEGORIES.keys():
        view.add_item(discord.ui.Button(label=f"{category} Weapons", style=discord.ButtonStyle.primary, custom_id=f"category_{category}"))

    await interaction.response.send_message(embed=embed, view=view)


# Command to display weapon categories and weapons
@bot.tree.command(name="weapon", description="Display weapon categories and weapons")
async def weapon(interaction: discord.Interaction):
    await show_weapon_categories(interaction)


# Handle interactions for category selection and pagination
@bot.event
async def on_interaction(interaction: discord.Interaction):
    if not interaction.data:
        return

    custom_id = interaction.data.get("custom_id", "")
    if custom_id.startswith("category_"):
        category = custom_id[9:]
        weapons = WEAPON_CATEGORIES.get(category, [])
        emoji = CATEGORY_EMOJIS.get(category, "")
        view = WeaponInfoView(weapons, category, emoji)
        await interaction.response.edit_message(embed=view.create_embed(), view=view)
    elif custom_id == "back_to_all":
        await show_weapon_categories(interaction)


class RanksView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

@bot.tree.command(name="ranks", description="Show player ranks based on ELO")
async def ranks(interaction: discord.Interaction):
    
    
    ranks = [
        ("Bronze", 1500, "<:bronze:1297740711617237064>"),
        ("Iron", 1600, "<:iron:1297740730101534730>"),
        ("Silver", 1700, "<:silver:1297740740314529812>"),
        ("Gold", 1800, "<:gold:1297740724347080785>"),
        ("Platinum", 1900, "<:platinum:1297740737307344916>"),
        ("Diamond", 2000, "<:diamond:1297740714821550121>"),
        ("Elite", 2100, "<:elite:1297740717803962400>"),
        ("Immortal", 2200, "<:immortal:1297740727433822342>"),
        ("Mythic", 2300, "<:mythic:1297740733968810064>"),
        ("Eternal", 2400, "<:eternal:1297740721226252338>")
    ]

    embed = discord.Embed(title="Player Ranks", color=discord.Color.blue())

    # Loop through ranks to find the player's current rank
    for rank, elo, emoji in ranks:
        
            embed.add_field(name=f"{emoji} {rank}", value=f"{elo}+ ELO", inline=False)
         

    # Add footer to the embed
    embed.set_footer(text="These ranks are only intended for this bot.")

    await interaction.response.send_message(embed=embed, view=RanksView())


VEHICLE_CATEGORIES = {
    "Tank": ["Tank Lvl-1", "Tank Lvl-2", "Tank Lvl-3"],
    "APC": ["APC Lvl-1", "APC Lvl-2", "APC Lvl-3"],
    "Heli": ["Heli Lvl-1", "Heli Lvl-2", "Heli Lvl-3"],
    "Jet": ["Jet Lvl-1", "Jet Lvl-2"]
}

VEHICLE_IMAGES = {
    "Tank Lvl-1": "https://i.imgur.com/2SnydKc.png",
    "Tank Lvl-2": "https://i.imgur.com/3JI6aSt.png",
    "Tank Lvl-3": "https://i.imgur.com/hflrHKC.png",
    "APC Lvl-1": "https://i.imgur.com/nLEIZFd.png",
    "APC Lvl-2": "https://i.imgur.com/hShPQ5F.png",
    "APC Lvl-3": "https://i.imgur.com/uXIimrX.png",
    "Heli Lvl-1": "https://i.imgur.com/p6RiOL5.png",
    "Heli Lvl-2": "https://i.imgur.com/vMyEGsc.png",
    "Heli Lvl-3": "https://i.imgur.com/wKtHpoo.png",
    "Jet Lvl-1": "https://i.imgur.com/ZyWeiCj.png",
    "Jet Lvl-2": "https://i.imgur.com/NfnuuDO.png"
}


VEHICLE_INFO = {
    "Tank Lvl-1": {
        "damage": {
            "Person": 275,
            "Tank": 275,
            "APC": 275,
            "Heli": 275,
            "Jet": 275
        },
        "maps": ["Desert", "Southwest", "Temple", "Kitchen"]
    },
    "Tank Lvl-2": {
        "damage": {
            "Person": 275,
            "Tank": 275,
            "APC": 275,
            "Heli": 275,
            "Jet": 275
        },
        "maps": ["Northwest", "Southwest", "Heist", "Cologne"]
    },
    "Tank Lvl-3": {
        "damage": {
            "Person": 275,
            "Tank": 275,
            "APC": 275,
            "Heli": 275,
            "Jet": 275
        },
        "maps": ["Pacific", "Southwest"]
    },
    "APC Lvl-1": {
        "damage": {
            "Person": 42.5,
            "Tank": 8.5,
            "APC": 17,
            "Heli": 17,
            "Jet": 17
        },
        "maps": ["Desert", "Temple", "Area 15 Base", "Kitchen"]
    },
    "APC Lvl-2": {
        "damage": {
            "Person": 42.5,
            "Tank": 8.5,
            "APC": 17,
            "Heli": 17,
            "Jet": 17
        },
        "maps": ["Northwest", "Heist", "Cologne"]
    },
    "APC Lvl-3": {
        "damage": {
            "Person": 42.5,
            "Tank": 8.5,
            "APC": 17,
            "Heli": 17,
            "Jet": 17
        },
        "maps": ["Pacific"]
    },
    "Heli Lvl-1": {
        "damage": {
            "Person": "?",
            "Tank": "?",
            "APC": "?",
            "Heli": "?",
            "Jet": "?"
        },
        "maps": ["Desert", "Kitchen"]
    },
    "Heli Lvl-2": {
        "damage": {
            "Person": "?",
            "Tank": "?",
            "APC": "?",
            "Heli": "?",
            "Jet": "?"
        },
        "maps": ["Northwest", "Temple", "Area 15 Base"]
    },
    "Heli Lvl-3": {
        "damage": {
            "Person": "?",
            "Tank": "?",
            "APC": "?",
            "Heli": "?",
            "Jet": "?"
        },
        "maps": ["Pacific"]
    },
    "Jet Lvl-1": {
        "damage": {
            "Person": 20,
            "Tank": 40,
            "APC": 40,
            "Heli": 40,
            "Jet": 80
        },
        "maps": ["Various"]
    },
    "Jet Lvl-2": {
        "damage": {
            "Person": 75,
            "Tank": 150,
            "APC": 150,
            "Heli": 150,
            "Jet": 300
        },
        "maps": ["Various"]
    }
}


# Create a vehicle information view
class VehicleInfoView(discord.ui.View):
    def __init__(self, vehicles: List[str], category: str):
        super().__init__(timeout=None)
        self.vehicles = vehicles
        self.category = category
        self.current_page = 0
        self.items_per_page = 1
        self.update_buttons()

    def create_embed(self):
        vehicle = self.vehicles[self.current_page]
        info = VEHICLE_INFO[vehicle]

        embed = discord.Embed(title=f"{vehicle} Information", color=discord.Color.green())

        # Add vehicle image
        embed.set_thumbnail(url=VEHICLE_IMAGES.get(vehicle, ""))

        # Add damage information
        damage_info = "\n".join([f"{target}: {amount}" for target, amount in info['damage'].items()])
        embed.add_field(name="Damage Values", value=damage_info, inline=False)

        # Add maps information
        maps_info = ", ".join(info['maps'])
        embed.add_field(name="Available Maps", value=maps_info, inline=False)

        embed.set_footer(text=f"Vehicle {self.current_page + 1} of {len(self.vehicles)}")
        return embed

    def update_buttons(self):
        self.clear_items()

        # Add navigation buttons
        if self.current_page > 0:
            self.add_item(discord.ui.Button(label="Previous", style=discord.ButtonStyle.primary, custom_id="prev_page"))
        if self.current_page < len(self.vehicles) - 1:
            self.add_item(discord.ui.Button(label="Next", style=discord.ButtonStyle.primary, custom_id="next_page"))

        # Add wiki button
        self.add_item(discord.ui.Button(
            label="View on Wiki",
            url="https://war-brokers.fandom.com/wiki/Vehicles",
            style=discord.ButtonStyle.link
        ))

        # Add back button
        self.add_item(discord.ui.Button(
            label="Back to Categories",
            style=discord.ButtonStyle.secondary,
            custom_id="back_categories"
        ))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        custom_id = interaction.data["custom_id"]

        if custom_id == "prev_page":
            self.current_page = max(0, self.current_page - 1)
        elif custom_id == "next_page":
            self.current_page = min(len(self.vehicles) - 1, self.current_page + 1)
        elif custom_id == "back_categories":
            await show_vehicle_categories(interaction)
            return False

        self.update_buttons()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)
        return True

async def show_vehicle_categories(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🚗 Vehicle Categories",
        description="Select a category to view available vehicles",
        color=discord.Color.blue()
    )

    # Add fields for each category
    for category, vehicles in VEHICLE_CATEGORIES.items():
        vehicle_list = "\n".join(vehicles)
        embed.add_field(name=category, value=vehicle_list, inline=False)

    # Create view with category buttons
    view = discord.ui.View(timeout=None)
    for category in VEHICLE_CATEGORIES.keys():
        view.add_item(discord.ui.Button(
            label=category,
            style=discord.ButtonStyle.primary,
            custom_id=f"category_{category}"
        ))

    await interaction.response.send_message(embed=embed, view=view)

@bot.tree.command(name="vehicle", description="Display vehicle information")
async def vehicle(interaction: discord.Interaction):
    await show_vehicle_categories(interaction)

# Event handler for button interactions
@bot.event
async def on_interaction(interaction: discord.Interaction):
    if not interaction.data:
        return

    custom_id = interaction.data.get("custom_id", "")
    if custom_id.startswith("category_"):
        category = custom_id[9:]  # Remove "category_" prefix
        vehicles = VEHICLE_CATEGORIES.get(category, [])
        view = VehicleInfoView(vehicles, category)
        await interaction.response.edit_message(embed=view.create_embed(), view=view)
# Run the bot
keep_alive()
bot.run(TOKEN)