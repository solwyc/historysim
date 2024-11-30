import requests
import json
import sqlite3
import os
import sys
from datetime import datetime
from rich import print
from rich.prompt import Prompt, Confirm
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.text import Text

# Determine the base path
def get_base_path():
    if getattr(sys, 'frozen', False):
        # If the application is run as a bundle, the PyInstaller bootloader
        # extends the sys module by a flag frozen=True and sets the app path
        return os.path.dirname(os.path.abspath(sys.argv[0]))
    else:
        return os.path.dirname(os.path.abspath(__file__))

# Configuration file path
BASE_PATH = get_base_path()
CONFIG_FILE = os.path.join(BASE_PATH, 'config.json')

console = Console()

def load_api_key():
    """
    Load the API keys from the config file.
    If the config file doesn't exist or the keys are missing, prompt the user to enter them.
    """
    try:
        config = {}
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
        else:
            console.print("[yellow]Config file not found. Creating a new one.[/yellow]")

        anthropic_api_key = config.get('anthropic_api_key')
        openai_api_key = config.get('openai_api_key')

        # Validate Anthropic API key
        if anthropic_api_key:
            if anthropic_api_key.startswith('sk-') and len(anthropic_api_key) > 10:
                console.print("[green]Anthropic API Key loaded.[/green]")
            else:
                console.print("[red]Invalid Anthropic API Key format in config. Prompting for input.[/red]")
                anthropic_api_key = None
        else:
            console.print("[yellow]Anthropic API key not found in config. Prompting for input.[/yellow]")

        # Prompt for Anthropic API key if missing or invalid
        if not anthropic_api_key:
            while True:
                anthropic_api_key = Prompt.ask("Enter your Anthropic API Key (sk-...)")
                anthropic_api_key = anthropic_api_key.strip()
                if anthropic_api_key.startswith('sk-') and len(anthropic_api_key) > 10:
                    break
                else:
                    console.print("[red]Invalid API Key format. It should start with 'sk-' and be longer than 10 characters.[/red]")

        # Validate OpenAI API key
        if openai_api_key:
            if openai_api_key.startswith('sk-') and len(openai_api_key) > 10:
                console.print("[green]OpenAI API Key loaded.[/green]")
            else:
                console.print("[red]Invalid OpenAI API Key format in config. Prompting for input.[/red]")
                openai_api_key = None
        else:
            console.print("[yellow]OpenAI API key not found in config. Prompting for input.[/yellow]")

        # Prompt for OpenAI API key if missing or invalid
        if not openai_api_key:
            while True:
                openai_api_key = Prompt.ask("Enter your OpenAI API Key (sk-...)")
                openai_api_key = openai_api_key.strip()
                if openai_api_key.startswith('sk-') and len(openai_api_key) > 10:
                    break
                else:
                    console.print("[red]Invalid API Key format. It should start with 'sk-' and be longer than 10 characters.[/red]")

        # Save the API keys to config file
        config = {
            'anthropic_api_key': anthropic_api_key,
            'openai_api_key': openai_api_key
        }
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f)
        console.print(f"[green]API Keys saved to '{CONFIG_FILE}'.[/green]")

        return anthropic_api_key, openai_api_key

    except IOError as io_err:
        console.print(f"[red]File I/O error occurred: {io_err}[/red]")
        exit(1)
    except json.JSONDecodeError:
        console.print("[red]Config file is corrupted. Please delete it and rerun the application.[/red]")
        exit(1)
    except Exception as e:
        console.print(f"[red]An unexpected error occurred: {e}[/red]")
        exit(1)

def prepare_anthropic_headers(api_key):
    """
    Prepare the headers for the Anthropic API request.
    """
    headers = {
        "x-api-key": api_key,
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01"
    }
    return headers

# === Added ===
def prepare_openai_headers(api_key):
    """
    Prepare the headers for the OpenAI API request.
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    return headers

# OpenAI API endpoint
OPENAI_API_URL = 'https://api.openai.com/v1/chat/completions'
# === End Added ===

# Anthropic API endpoint
ANTHROPIC_API_URL = 'https://api.anthropic.com/v1/messages'

def initialize_database():
    """
    Initialize the database and ensure all necessary tables exist.
    """
    try:
        conn = sqlite3.connect(os.path.join(BASE_PATH, 'reports.db'))
        c = conn.cursor()

        # Create reports table if it doesn't exist
        c.execute('''
            CREATE TABLE IF NOT EXISTS reports (
                report_number INTEGER PRIMARY KEY AUTOINCREMENT,
                report_text TEXT,
                created_at TEXT,
                world_description TEXT
            )
        ''')

        # Create simulations table if it doesn't exist
        c.execute('''
            CREATE TABLE IF NOT EXISTS simulations (
                simulation_id INTEGER PRIMARY KEY AUTOINCREMENT,
                simulation_name TEXT,
                messages TEXT,
                created_at TEXT,
                report_number INTEGER,
                FOREIGN KEY(report_number) REFERENCES reports(report_number)
            )
        ''')

        conn.commit()
    except sqlite3.Error as db_err:
        raise Exception(f"Database error occurred during initialization: {db_err}")
    finally:
        conn.close()

def generate_world(api_url, headers, start_year, notes):
    """
    Generate a detailed world based on the starting year and notes.
    """
    system_prompt = (
        "You are an AI assistant tasked with creating a detailed and comprehensive description of a fictional world. "
        "The description should include the following sections with clear headings:\n\n"
        "1. **World Overview**\n"
        "2. **Geography and Climate**\n"
        "3. **Society and Culture**\n"
        "4. **Technological Landscape**\n"
        "5. **Historical Events Leading to Divergence**\n\n"
        "Ensure that each section is thorough and provides in-depth information. Base the creation on the following parameters:\n\n"
        f"- **Starting Year**: {start_year}\n"
        f"- **Notes/Changes**: {notes}\n\n"
        "Please generate the world description following the above structure."
    )

    user_message = "Please create the world description based on the provided parameters."

    payload = {
        "model": "claude-3-5-sonnet-latest",
        "system": system_prompt,
        "messages": [
            {"role": "user", "content": user_message}
        ],
        "max_tokens": 8192,  # Adjusted to a lower value
        "temperature": 0.7
    }

    with Progress(SpinnerColumn(), TextColumn("[bold blue]Generating world description..."), transient=True) as progress:
        task = progress.add_task("world_generation")
        try:
            response = requests.post(api_url, headers=headers, data=json.dumps(payload))
            response.raise_for_status()  # Raises HTTPError for bad responses
            data = response.json()

            # Extract the world description from data['content']
            content = data.get('content', [])
            world_description = ''
            for item in content:
                if item.get('type') == 'text':
                    world_description += item.get('text', '')
            world_description = world_description.strip()

            if not world_description:
                console.print("[red]No world description received from the API.[/red]")
                console.print(f"[yellow]Response data: {json.dumps(data, indent=2)}[/yellow]")
                return None

            progress.update(task, completed=True)
            return world_description
        except requests.exceptions.HTTPError as http_err:
            progress.stop()
            try:
                error_details = response.json()
                console.print(f"[red]HTTP error occurred while generating world: {http_err}[/red]")
                console.print(f"[red]Error details: {json.dumps(error_details, indent=2)}[/red]")
            except json.JSONDecodeError:
                console.print(f"[red]HTTP error occurred while generating world: {http_err}[/red]")
                console.print(f"[red]Response Text: {response.text}[/red]")
            raise
        except Exception as err:
            progress.stop()
            raise Exception(f"[red]An error occurred while generating world: {err}[/red]")

def generate_report(api_url, headers, start_year, notes, world_description):
    """
    Generate the divergent timeline report following a specific format.
    """
    system_prompt = (
        "You are an agent working for the Multiversal Investigation Bureau. "
        "Using the provided world description, generate a detailed academic 'Divergent Timeline' report starting from the year "
        f"{start_year}. The report must adhere to the following structure with clear headings and subheadings:\n\n"
        "1. **Introduction**\n"
        "   - Overview of the point of divergence.\n"
        "2. **Significant Events**\n"
        "   - Detailed analysis of key events that shaped the alternate timeline.\n"
        "3. **Societal Changes**\n"
        "   - Examination of how society evolved differently.\n"
        "4. **Technological Advancements**\n"
        "   - Exploration of technological developments unique to this timeline.\n"
        "5. **Economic and Political Impacts**\n"
        "   - Analysis of economic and political structures in the alternate world.\n"
        "6. **MIB Interactions/Investigations**\n"
        "   - Summary of any Multiversal Investigation Bureau transdimensional sorties or missions in this universe.\n"
        "7. **Conclusion**\n"
        "   - Summary of the divergent timeline and its implications.\n\n"
        "Ensure that each section is comprehensive, well-organized, and clearly labeled. Incorporate insights from the following world description:\n\n"
        f"{world_description}\n\n"
        "Please generate the report following the above structure."
    )

    user_message = "Please generate the divergent timeline report based on the provided world description."

    payload = {
        "model": "claude-3-5-sonnet-latest",
        "system": system_prompt,
        "messages": [
            {"role": "user", "content": user_message}
        ],
        "max_tokens": 8192,  # Adjusted to a reasonable value
        "temperature": 0.7
    }

    with Progress(SpinnerColumn(), TextColumn("[bold green]Generating divergent timeline report..."), transient=True) as progress:
        task = progress.add_task("report_generation")
        try:
            response = requests.post(api_url, headers=headers, data=json.dumps(payload))
            response.raise_for_status()
            data = response.json()

            # Extract the report text from data['content']
            content = data.get('content', [])
            report_text = ''
            for item in content:
                if item.get('type') == 'text':
                    report_text += item.get('text', '')
            report_text = report_text.strip()

            if not report_text:
                console.print("[red]No report text received from the API.[/red]")
                console.print(f"[yellow]Response data: {json.dumps(data, indent=2)}[/yellow]")
                return None

            progress.update(task, completed=True)
            return report_text
        except requests.exceptions.HTTPError as http_err:
            progress.stop()
            try:
                error_details = response.json()
                console.print(f"[red]HTTP error occurred while generating report: {http_err}[/red]")
                console.print(f"[red]Error details: {json.dumps(error_details, indent=2)}[/red]")
            except json.JSONDecodeError:
                console.print(f"[red]HTTP error occurred while generating report: {http_err}[/red]")
                console.print(f"[red]Response Text: {response.text}[/red]")
            raise
        except Exception as err:
            progress.stop()
            raise Exception(f"[red]An error occurred while generating report: {err}[/red]")

def save_report(report_text, world_description):
    """
    Save the report and world description to a SQLite database and a text file.
    Returns the report number and filename.
    """
    try:
        conn = sqlite3.connect(os.path.join(BASE_PATH, 'reports.db'))
        c = conn.cursor()

        # Create table if it doesn't exist
        c.execute('''
            CREATE TABLE IF NOT EXISTS reports (
                report_number INTEGER PRIMARY KEY AUTOINCREMENT,
                report_text TEXT,
                created_at TEXT,
                world_description TEXT
            )
        ''')

        # Insert the report with a timestamp
        timestamp = datetime.now().isoformat()
        c.execute("INSERT INTO reports (report_text, created_at, world_description) VALUES (?, ?, ?)",
                  (report_text, timestamp, world_description))
        report_number = c.lastrowid
        conn.commit()
    except sqlite3.Error as db_err:
        raise Exception(f"Database error occurred: {db_err}")
    finally:
        conn.close()

    # Save the report to a text file
    report_filename = os.path.join(BASE_PATH, f"Report_{report_number}.txt")
    try:
        with open(report_filename, 'w', encoding='utf-8') as f:
            f.write(report_text)
    except IOError as io_err:
        raise Exception(f"[red]File I/O error occurred while saving the report: {io_err}[/red]")

    return report_number, report_filename

def list_reports():
    """
    List all saved reports from the database.
    """
    try:
        conn = sqlite3.connect(os.path.join(BASE_PATH, 'reports.db'))
        c = conn.cursor()
        c.execute("SELECT report_number, created_at FROM reports ORDER BY report_number DESC")
        rows = c.fetchall()
        conn.close()

        if not rows:
            console.print("[yellow]No reports found.[/yellow]")
            return

        table = Table(title="Saved Reports", show_lines=True)
        table.add_column("Report Number", style="cyan", justify="right")
        table.add_column("Created At", style="magenta")

        for row in rows:
            table.add_row(str(row[0]), row[1])

        console.print(table)

    except sqlite3.Error as db_err:
        console.print(f"[red]Database error occurred: {db_err}[/red]")

def view_report():
    """
    View a specific report by report number.
    """
    list_reports()
    report_number = Prompt.ask("Enter the Report Number you want to view", default="")

    if not report_number.isdigit():
        console.print("[red]Invalid Report Number.[/red]")
        return

    try:
        conn = sqlite3.connect(os.path.join(BASE_PATH, 'reports.db'))
        c = conn.cursor()
        c.execute("SELECT report_text, world_description, created_at FROM reports WHERE report_number = ?", (int(report_number),))
        row = c.fetchone()
        conn.close()

        if not row:
            console.print(f"[red]Report #{report_number} not found.[/red]")
            return

        report_text, world_description, created_at = row
        if not report_text:
            console.print(f"[red]Report #{report_number} has no content.[/red]")
            return

        panel = Panel(Text(report_text, style="white"), title=f"Report #{report_number} - Created At: {created_at}", border_style="green")
        console.print(panel)
    except sqlite3.Error as db_err:
        console.print(f"[red]Database error occurred: {db_err}[/red]")

def delete_report():
    """
    Delete a specific report by report number.
    """
    list_reports()
    report_number = Prompt.ask("Enter the Report Number you want to delete", default="")

    if not report_number.isdigit():
        console.print("[red]Invalid Report Number.[/red]")
        return

    confirm = Confirm.ask(f"Are you sure you want to delete Report #{report_number}?")
    if not confirm:
        console.print("[yellow]Deletion cancelled.[/yellow]")
        return

    try:
        conn = sqlite3.connect(os.path.join(BASE_PATH, 'reports.db'))
        c = conn.cursor()
        c.execute("DELETE FROM reports WHERE report_number = ?", (int(report_number),))
        if c.rowcount == 0:
            console.print(f"[red]Report #{report_number} not found.[/red]")
        else:
            conn.commit()
            console.print(f"[green]Report #{report_number} has been deleted successfully.[/green]")
        conn.close()

        # Optionally, delete the corresponding text file
        report_filename = os.path.join(BASE_PATH, f"Report_{report_number}.txt")
        if os.path.exists(report_filename):
            os.remove(report_filename)
            console.print(f"[green]Deleted file '{report_filename}'.[/green]")
    except sqlite3.Error as db_err:
        console.print(f"[red]Database error occurred: {db_err}[/red]")
    except Exception as e:
        console.print(f"[red]An error occurred: {e}[/red]")

def create_simulation(simulation_name, messages, report_number):
    """
    Create a new simulation entry in the database.
    """
    try:
        conn = sqlite3.connect(os.path.join(BASE_PATH, 'reports.db'))
        c = conn.cursor()

        messages_json = json.dumps(messages)

        c.execute('''
            INSERT INTO simulations (simulation_name, messages, created_at, report_number)
            VALUES (?, ?, ?, ?)
        ''', (simulation_name, messages_json, datetime.now().isoformat(), report_number))

        simulation_id = c.lastrowid

        conn.commit()
        return simulation_id
    except sqlite3.Error as db_err:
        raise Exception(f"Database error occurred while creating simulation: {db_err}")
    finally:
        conn.close()

def save_simulation(simulation_id, messages):
    """
    Save the simulation messages to the database.
    """
    try:
        conn = sqlite3.connect(os.path.join(BASE_PATH, 'reports.db'))
        c = conn.cursor()

        messages_json = json.dumps(messages)

        c.execute('''
            UPDATE simulations
            SET messages = ?, created_at = ?
            WHERE simulation_id = ?
        ''', (messages_json, datetime.now().isoformat(), simulation_id))

        conn.commit()
    except sqlite3.Error as db_err:
        raise Exception(f"Database error occurred while saving simulation: {db_err}")
    finally:
        conn.close()

def load_simulation(simulation_id):
    """
    Load simulation messages from the database.
    Returns the messages list and associated report_number.
    """
    try:
        conn = sqlite3.connect(os.path.join(BASE_PATH, 'reports.db'))
        c = conn.cursor()

        c.execute('''
            SELECT messages, report_number
            FROM simulations
            WHERE simulation_id = ?
        ''', (simulation_id,))

        row = c.fetchone()
        if not row:
            raise Exception(f"Simulation ID {simulation_id} not found.")

        messages_json, report_number = row
        messages = json.loads(messages_json)

        return messages, report_number
    except sqlite3.Error as db_err:
        raise Exception(f"Database error occurred while loading simulation: {db_err}")
    finally:
        conn.close()

def chat_with_chrono(api_url, headers):
    """
    Allow the user to chat with Chrono about a selected report.
    Maintains chat history for each report.
    """
    # List available reports
    list_reports()
    report_number = Prompt.ask("Enter the Report Number you want to discuss with Chrono", default="")

    if not report_number.isdigit():
        console.print("[red]Invalid Report Number.[/red]")
        return

    report_number = int(report_number)

    try:
        # Retrieve the selected report
        conn = sqlite3.connect(os.path.join(BASE_PATH, 'reports.db'))
        c = conn.cursor()
        c.execute("SELECT report_text, created_at FROM reports WHERE report_number = ?", (report_number,))
        row = c.fetchone()
        conn.close()

        if not row:
            console.print(f"[red]Report #{report_number} not found.[/red]")
            return

        report_text, created_at = row

        # Define a unique simulation name for Chrono chat per report
        simulation_name = f"chrono_chat_report_{report_number}"

        # Attempt to load existing simulation (chat history) for this report
        try:
            conn = sqlite3.connect(os.path.join(BASE_PATH, 'reports.db'))
            c = conn.cursor()
            c.execute("SELECT simulation_id, messages FROM simulations WHERE simulation_name = ? AND report_number = ?", 
                      (simulation_name, report_number))
            sim_row = c.fetchone()
            conn.close()

            if sim_row:
                simulation_id, messages_json = sim_row
                messages = json.loads(messages_json)
                console.print(f"[green]Loaded existing chat history for Report #{report_number}.[/green]\n")
            else:
                # Initialize messages with initial user message
                messages = [
                    {"role": "user", "content": f"I would like to discuss Report #{report_number}. Here is the report:\n\n{report_text}"}
                ]
                # Create a new simulation entry
                simulation_id = create_simulation(simulation_name, messages, report_number)
                console.print(f"[green]Started a new chat with Chrono for Report #{report_number}.[/green]\n")
        except sqlite3.Error as db_err:
            console.print(f"[red]Database error occurred while loading/saving simulation: {db_err}[/red]")
            return

        # Modify system prompt to encourage creativity
        system_prompt = (
            "You are Chrono, an advanced AI assistant working for the Multiversal Investigation Bureau. "
            "You have access to detailed reports about various simulations of divergent timelines. "
            "Use the information from the selected report and your own extensive knowledge and creativity to engage in a meaningful and informative conversation. "
            "Feel free to elaborate and provide additional details about the world, even if they are not explicitly mentioned in the report, as long as they are consistent with the given information."
        )

        console.print(f"[bold cyan]Starting chat with Chrono about Report #{report_number}.[/bold cyan]")
        console.print("[bold magenta]Type 'exit' or 'quit' to end the chat.[/bold magenta]\n")

        while True:
            user_input = Prompt.ask("[bold green]You[/bold green]").strip()
            if user_input.lower() in ['exit', 'quit']:
                console.print("[bold cyan]Ending chat with Chrono.[/bold cyan]")
                break

            # Append user message to conversation history
            messages.append({"role": "user", "content": user_input})

            # Prepare payload for API
            payload = {
                "model": "claude-3-5-sonnet-latest",
                "system": system_prompt,
                "messages": messages,
                "max_tokens": 8192,
                "temperature": 0.7
            }

            try:
                with Progress(SpinnerColumn(), TextColumn("[bold blue]Chrono is responding..."), transient=True) as progress:
                    task = progress.add_task("chatting")
                    response = requests.post(api_url, headers=headers, data=json.dumps(payload))
                    response.raise_for_status()
                    data = response.json()

                    # Extract Chrono's response from data['content']
                    content = data.get('content', [])
                    chrono_response = ''
                    for item in content:
                        if item.get('type') == 'text':
                            chrono_response += item.get('text', '')
                    chrono_response = chrono_response.strip()

                    if not chrono_response:
                        console.print("[red]No response received from Chrono.[/red]")
                        console.print(f"[yellow]Response data: {json.dumps(data, indent=2)}[/yellow]")
                        continue

                    progress.update(task, completed=True)

            except requests.exceptions.HTTPError as http_err:
                progress.stop()
                try:
                    error_details = response.json()
                    console.print(f"[red]HTTP error occurred while chatting with Chrono: {http_err}[/red]")
                    console.print(f"[red]Error details: {json.dumps(error_details, indent=2)}[/red]")
                except json.JSONDecodeError:
                    console.print(f"[red]HTTP error occurred while chatting with Chrono: {http_err}[/red]")
                    console.print(f"[red]Response Text: {response.text}[/red]")
                raise
            except Exception as err:
                progress.stop()
                raise Exception(f"[red]An error occurred while chatting with Chrono: {err}[/red}}")

            # Display Chrono's response outside the progress bar context
            console.print(f"[bold blue]Chrono[/bold blue]: {chrono_response}\n")

            # Append Chrono's response to conversation history
            messages.append({"role": "assistant", "content": chrono_response})

            # Save the updated conversation history to the simulation
            try:
                save_simulation(simulation_id, messages)
            except Exception as save_err:
                console.print(f"[red]Failed to save chat history: {save_err}[/red]")
                # Continue the chat even if saving fails

    except sqlite3.Error as db_err:
        console.print(f"[red]Database error occurred while retrieving report: {db_err}[/red]")
    except Exception as e:
        console.print(f"[red]An unexpected error occurred: {e}[/red]")

def explore_timeline_as_avatar(anthropic_api_url, anthropic_headers, openai_api_url, openai_headers):
    """
    Allow the user to explore a timeline as an avatar.
    """
    console.print("\n[bold underline]Timeline Avatar Simulation[/bold underline]\n")
    table = Table(show_header=False, box=None)
    table.add_row("1.", "Start a new simulation")
    table.add_row("2.", "Continue an existing simulation")
    console.print(table)

    choice = Prompt.ask("Choose an option", choices=["1", "2"], default="1")

    if choice == "1":
        # Start a new simulation
        # List available reports
        list_reports()
        report_number = Prompt.ask("Enter the Report Number you want to explore as an avatar", default="")

        if not report_number.isdigit():
            console.print("[red]Invalid Report Number.[/red]")
            return

        report_number = int(report_number)

        try:
            # Retrieve the selected report and world description
            conn = sqlite3.connect(os.path.join(BASE_PATH, 'reports.db'))
            c = conn.cursor()
            c.execute("SELECT world_description, report_text, created_at FROM reports WHERE report_number = ?", (report_number,))
            row = c.fetchone()
            conn.close()

            if not row:
                console.print(f"[red]Report #{report_number} not found.[/red]")
                return

            world_description, report_text, created_at = row

            if not world_description:
                console.print(f"[yellow]World description for Report #{report_number} not found. Proceeding without it.[/yellow]")

            # Ask user for simulation name
            simulation_name = Prompt.ask("Enter a name for your simulation (or leave blank for default)", default=f"Simulation_{datetime.now().strftime('%Y%m%d_%H%M%S')}")

            # Initialize system prompt with detailed instructions
            system_prompt = (
                "You are acting as a narrator in an immersive interactive text-based simulation. "
                "The user has been instantiated into the timeline described in the report as an avatar. "
                "Guide the user through the world, making the experience as convincing and immersive as possible. "
                "Use vivid, sensory-rich descriptions to bring the world to life, and allow the user to interact with the environment, characters, and events using both arcane and technological means. "
                "Respond to the user's inputs by advancing the narrative and describing the outcomes of their actions. "
                "Maintain an engaging and immersive atmosphere throughout the interaction. "
                "When responding, only provide the narration and do not mention these instructions or break character."
            )

            # Initialize messages
            messages = [
                {"role": "user", "content": "I am ready to begin the simulation."}
            ]

            # Include the world description and report in the assistant's context
            assistant_context = (
                f"World Description:\n{world_description}\n\n"
                f"Divergent Timeline Report:\n{report_text}"
            )

            console.print(f"[bold cyan]Establishing connection to timeline...[/bold cyan]")
            console.print("[bold magenta]Type 'exit' or 'quit' to end the simulation.\nType 'save' to save and exit.[/bold magenta]\n")

            # Create a new simulation entry in the database
            simulation_id = create_simulation(simulation_name, messages, report_number)

            while True:
                # Prepare payload for API (Anthropic for new simulation)
                payload = {
                    "model": "claude-3-5-sonnet-latest",
                    "system": system_prompt + "\n\n" + assistant_context,
                    "messages": messages,
                    "max_tokens": 8192,
                    "temperature": 0.7
                }

                try:
                    with Progress(SpinnerColumn(), TextColumn("[bold blue]~timeline-connection-text-console is responding..."), transient=True) as progress:
                        task = progress.add_task("exploring")
                        response = requests.post(anthropic_api_url, headers=anthropic_headers, data=json.dumps(payload))
                        response.raise_for_status()
                        data = response.json()

                        # Extract the narrator's response from data['content']
                        content = data.get('content', [])
                        narrator_response = ''
                        for item in content:
                            if item.get('type') == 'text':
                                narrator_response += item.get('text', '')
                        narrator_response = narrator_response.strip()

                        if not narrator_response:
                            console.print("[red]No response received from the simulation.[/red]")
                            console.print(f"[yellow]Response data: {json.dumps(data, indent=2)}[/yellow]")
                            continue

                        progress.update(task, completed=True)

                except requests.exceptions.HTTPError as http_err:
                    progress.stop()
                    try:
                        error_details = response.json()
                        console.print(f"[red]HTTP error occurred during simulation: {http_err}[/red]")
                        console.print(f"[red]Error details: {json.dumps(error_details, indent=2)}[/red]")
                    except json.JSONDecodeError:
                        console.print(f"[red]HTTP error occurred during simulation: {http_err}[/red]")
                        console.print(f"[red]Response Text: {response.text}[/red]")
                    raise
                except Exception as err:
                    progress.stop()
                    raise Exception(f"[red]An error occurred during simulation: {err}[/red]")

                # Display Narrator's response outside the progress bar context
                console.print(f"[bold blue]~timeline-connection-text-console[/bold blue]: {narrator_response}\n")

                # Append Narrator's response to conversation history
                messages.append({"role": "assistant", "content": narrator_response})

                # Save the simulation messages
                save_simulation(simulation_id, messages)

                # Get user input
                user_input = Prompt.ask("[bold green]You[/bold green]").strip()
                if user_input.lower() in ['exit', 'quit', 'save']:
                    console.print("[bold cyan]Ending simulation.[/bold cyan]")
                    break

                # Append user message to conversation history
                messages.append({"role": "user", "content": user_input})

                # Save the simulation messages
                save_simulation(simulation_id, messages)

        except sqlite3.Error as db_err:
            console.print(f"[red]Database error occurred while retrieving report: {db_err}[/red]")
        except Exception as e:
            console.print(f"[red]An unexpected error occurred: {e}[/red]")

    elif choice == "2":
        # Continue an existing simulation
        try:
            # List existing simulations
            conn = sqlite3.connect(os.path.join(BASE_PATH, 'reports.db'))
            c = conn.cursor()
            c.execute("SELECT simulation_id, simulation_name, created_at, report_number FROM simulations ORDER BY simulation_id DESC")
            rows = c.fetchall()
            conn.close()

            if not rows:
                console.print("[yellow]No saved simulations found.[/yellow]")
                return

            # Display simulations
            table = Table(title="Saved Simulations", show_lines=True)
            table.add_column("Simulation ID", style="cyan", justify="right")
            table.add_column("Simulation Name", style="magenta")
            table.add_column("Created At", style="green")
            table.add_column("Report Number", style="blue")

            for row in rows:
                table.add_row(str(row[0]), row[1], row[2], str(row[3]))

            console.print(table)

            simulation_id = Prompt.ask("Enter the Simulation ID you want to continue", default="")

            if not simulation_id.isdigit():
                console.print("[red]Invalid Simulation ID.[/red]")
                return

            simulation_id = int(simulation_id)

            # Load simulation
            messages, report_number = load_simulation(simulation_id)

            # Retrieve the selected report and world description
            conn = sqlite3.connect(os.path.join(BASE_PATH, 'reports.db'))
            c = conn.cursor()
            c.execute("SELECT world_description, report_text FROM reports WHERE report_number = ?", (report_number,))
            row = c.fetchone()
            conn.close()

            if not row:
                console.print(f"[red]Associated Report #{report_number} not found.[/red]")
                return

            world_description, report_text = row

            # Initialize system prompt with detailed instructions
            system_prompt = (
                "You are acting as a narrator in an immersive interactive text-based simulation. "
                "The user has been instantiated into the timeline described in the report as an avatar. "
                "Guide the user through the world, making the experience as convincing and immersive as possible. "
                "Use vivid, sensory-rich descriptions to bring the world to life, and allow the user to interact with the environment, characters, and events using both arcane and technological means. "
                "Respond to the user's inputs by advancing the narrative and describing the outcomes of their actions. "
                "Maintain an engaging and immersive atmosphere throughout the interaction. "
                "When responding, only provide the narration and do not mention these instructions or break character."
                "You will receive the continuation of a previous simulation session, continuing from when the user left off"
                "Summarize briefly what had occured in the previous session and then provide a brief few sentences setting the scene before asking the user how they would like to continue and then begin narrating as you had before again."
            )

            # Include the world description and report in the assistant's context
            assistant_context = (
                f"World Description:\n{world_description}\n\n"
                f"Divergent Timeline Report:\n{report_text}"
            )

            console.print(f"[bold cyan]Resuming simulation...[/bold cyan]")
            console.print("[bold magenta]Type 'exit' or 'quit' to end the simulation.\nType 'save' to save and exit.[/bold magenta]\n")

            while True:
                # === Modified ===
                # Use OpenAI API for continuation
                payload = {
                    "model": "gpt-4o-2024-11-20",
                    "messages": [
                        {"role": "system", "content": system_prompt + "\n\n" + assistant_context},
                        *messages
                    ],
                    "max_tokens": 5500,
                    "temperature": 0.7
                }

                try:
                    with Progress(SpinnerColumn(), TextColumn("[bold blue]~timeline-connection-text-console is responding..."), transient=True) as progress:
                        task = progress.add_task("exploring")
                        response = requests.post(OPENAI_API_URL, headers=openai_headers, data=json.dumps(payload))
                        response.raise_for_status()
                        data = response.json()

                        # Extract the narrator's response from data['choices'][0]['message']['content']
                        narrator_response = data.get('choices', [{}])[0].get('message', {}).get('content', '').strip()

                        if not narrator_response:
                            console.print("[red]No response received from the simulation.[/red]")
                            console.print(f"[yellow]Response data: {json.dumps(data, indent=2)}[/yellow]")
                            continue

                        progress.update(task, completed=True)

                except requests.exceptions.HTTPError as http_err:
                    progress.stop()
                    try:
                        error_details = response.json()
                        console.print(f"[red]HTTP error occurred during simulation: {http_err}[/red]")
                        console.print(f"[red]Error details: {json.dumps(error_details, indent=2)}[/red]")
                    except json.JSONDecodeError:
                        console.print(f"[red]HTTP error occurred during simulation: {http_err}[/red]")
                        console.print(f"[red]Response Text: {response.text}[/red]")
                    raise
                except Exception as err:
                    progress.stop()
                    raise Exception(f"[red]An error occurred during simulation: {err}[/red]")
                # === End Modified ===

                # Display Narrator's response outside the progress bar context
                console.print(f"[bold blue]~timeline-connection-text-console[/bold blue]: {narrator_response}\n")

                # Append Narrator's response to conversation history
                messages.append({"role": "assistant", "content": narrator_response})

                # Save the simulation messages
                save_simulation(simulation_id, messages)

                # Get user input
                user_input = Prompt.ask("[bold green]You[/bold green]").strip()
                if user_input.lower() in ['exit', 'quit', 'save']:
                    console.print("[bold cyan]Ending simulation.[/bold cyan]")
                    break

                # Append user message to conversation history
                messages.append({"role": "user", "content": user_input})

                # Save the simulation messages
                save_simulation(simulation_id, messages)

        except sqlite3.Error as db_err:
            console.print(f"[red]Database error occurred while retrieving simulations: {db_err}[/red]")
        except Exception as e:
            console.print(f"[red]An unexpected error occurred: {e}[/red]")

def generate_new_report(anthropic_api_key, openai_api_key):
    """
    Handle the process of generating a new report.
    """
    try:
        # Initialize the database
        initialize_database()

        # Get user input with prompts
        start_year = Prompt.ask("Enter the starting year for the point of divergence", default="")
        if not start_year.isdigit():
            console.print("[red]Starting year must be a valid integer.[/red]")
            return

        notes = Prompt.ask("Enter any notes or changes you want to include in the simulation", default="")
        if not notes:
            console.print("[red]Notes cannot be empty.[/red]")
            return

        # Prepare headers
        anthropic_headers = prepare_anthropic_headers(anthropic_api_key)
        openai_headers = prepare_openai_headers(openai_api_key)

        # Generate the world description using Anthropic API
        world_description = generate_world(ANTHROPIC_API_URL, anthropic_headers, start_year, notes)
        if not world_description:
            console.print("[red]Failed to generate world description. Aborting report generation.[/red]")
            return
        console.print("[green]World description generated successfully.[/green]\n")

        # Generate the report using Anthropic API
        report_text = generate_report(ANTHROPIC_API_URL, anthropic_headers, start_year, notes, world_description)
        if not report_text:
            console.print("[red]Failed to generate report. Aborting.[/red]")
            return
        console.print("[green]Divergent timeline report generated successfully.[/green]\n")

        # Save the report and world description
        report_number, report_filename = save_report(report_text, world_description)

        # Display the report
        report_panel = Panel(Text(report_text, style="white"), title=f"Simulation Report (Report #{report_number})", border_style="blue")
        console.print(report_panel)
        console.print(f"[bold green]The report has been saved as '{report_filename}' and stored in the database (Report #{report_number}).[/bold green]")
    except Exception as e:
        console.print(f"[red]An error occurred: {e}[/red]")

def main_menu(anthropic_api_key, openai_api_key):
    """
    Display the main menu and handle user selections.
    """
    anthropic_headers = prepare_anthropic_headers(anthropic_api_key)
    openai_headers = prepare_openai_headers(openai_api_key)

    while True:
        console.print("\n[bold underline]Divergent Timeline Report Generator[/bold underline]\n")
        table = Table(show_header=False, box=None)
        table.add_row("1.", "Generate a new report")
        table.add_row("2.", "View existing reports")
        table.add_row("3.", "Delete a report")
        table.add_row("4.", "Chat with Chrono about a report")
        table.add_row("5.", "Explore a timeline as an avatar")
        table.add_row("6.", "Exit")
        console.print(table)

        choice = Prompt.ask("Choose an option", choices=["1", "2", "3", "4", "5", "6"], default="1")

        if choice == "1":
            generate_new_report(anthropic_api_key, openai_api_key)
        elif choice == "2":
            view_report()
        elif choice == "3":
            delete_report()
        elif choice == "4":
            chat_with_chrono(ANTHROPIC_API_URL, anthropic_headers)
        elif choice == "5":
            explore_timeline_as_avatar(ANTHROPIC_API_URL, anthropic_headers, OPENAI_API_URL, openai_headers)
        elif choice == "6":
            console.print("[bold cyan]Goodbye![/bold cyan]")
            break

def main():
    """
    Entry point of the script.
    """
    initialize_database()
    anthropic_api_key, openai_api_key = load_api_key()
    main_menu(anthropic_api_key, openai_api_key)


if __name__ == "__main__":
    main()