"""
Command-line client for Ansari API.

This client connects to the Ansari API endpoints provided by main_api.py and
offers a similar interface to main_stdio.py.
"""

import logging
import typer
import requests
import random
import string
import time
from typing import Optional
from rich.console import Console
from rich.prompt import Prompt

from ansari.ansari_logger import get_logger

logger = get_logger(__name__)
app = typer.Typer()
console = Console()


class AnsariApiClient:
    """Client for interacting with the Ansari API."""

    def __init__(
        self, base_url, email=None, password=None, origin="http://localhost:3000", mobile_header=False, json_mode=False
    ):
        self.base_url = base_url
        self.email = email
        self.password = password
        self.access_token = None
        self.refresh_token = None
        self.headers = {
            "Content-Type": "application/json",
            "Origin": origin,
        }
        # Add mobile header to bypass CORS if enabled
        if mobile_header:
            self.headers["x-mobile-ansari"] = "ANSARI"
        self.user_info = None
        self.is_guest = False
        self.json_mode = json_mode

    def login(self):
        """Authenticate with the API using email and password."""
        url = self.add_host_header(f"{self.base_url}/api/v2/users/login")
        response = requests.post(url, json={"email": self.email, "password": self.password}, headers=self.headers)
        if response.status_code == 200:
            data = response.json()
            self.access_token = data["access_token"]
            self.refresh_token = data["refresh_token"]
            self.headers["Authorization"] = f"Bearer {self.access_token}"
            self.user_info = {"first_name": data["first_name"], "last_name": data["last_name"]}
            return True
        logger.error(f"Login failed: {response.status_code} {response.text}")
        return False

    def register_guest(self):
        """Register a new guest user account."""
        # Generate random guest credentials
        random_id = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
        timestamp = int(time.time())
        self.email = f"guest_{random_id}_{timestamp}@guest.ansari.chat"
        self.password = "".join(random.choices(string.ascii_letters + string.digits + "!@#$%^&*", k=16))

        # Register the guest account
        url = self.add_host_header(f"{self.base_url}/api/v2/users/register")
        response = requests.post(
            url,
            json={"email": self.email, "password": self.password, "first_name": "Guest", "last_name": f"User_{random_id[:4]}"},
            headers=self.headers,
        )

        if response.status_code == 200:
            logger.info(f"Guest account registered: {self.email}")
            self.is_guest = True
            # Now login with the new credentials
            return self.login()
        logger.error(f"Guest registration failed: {response.status_code} {response.text}")
        return False

    def create_thread(self):
        """Create a new conversation thread."""
        url = self.add_host_header(f"{self.base_url}/api/v2/threads")
        response = requests.post(url, headers=self.headers)
        if response.status_code == 200:
            return response.json()
        logger.error(f"Create thread failed: {response.status_code} {response.text}")
        return None

    def send_message(self, thread_id, content):
        """Send a message to a thread and get the response."""
        url = self.add_host_header(f"{self.base_url}/api/v2/threads/{thread_id}")

        # If in JSON mode, we don't want streaming
        stream_mode = not self.json_mode

        response = requests.post(url, json={"role": "user", "content": content}, headers=self.headers, stream=stream_mode)

        if response.status_code == 200:
            # Set the correct encoding for the response
            if stream_mode:
                response.encoding = "utf-8"
            return response
        logger.error(f"Send message failed: {response.status_code} {response.text}")
        return None

    def get_thread(self, thread_id):
        """Get thread history."""
        url = self.add_host_header(f"{self.base_url}/api/v2/threads/{thread_id}")
        response = requests.get(url, headers=self.headers)
        if response.status_code == 200:
            return response.json()
        logger.error(f"Get thread failed: {response.status_code} {response.text}")
        return None

    def get_all_threads(self):
        """Get all user threads."""
        url = self.add_host_header(f"{self.base_url}/api/v2/threads")
        response = requests.get(url, headers=self.headers)
        if response.status_code == 200:
            return response.json()
        logger.error(f"Get all threads failed: {response.status_code} {response.text}")
        return None

    def refresh_auth_token(self):
        """Refresh the authentication token."""
        if not self.refresh_token:
            return False

        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.refresh_token}"}

        # Add Origin header for CORS validation
        if "Origin" in self.headers:
            headers["Origin"] = self.headers["Origin"]

        response = requests.post(f"{self.base_url}/api/v2/users/refresh_token", headers=headers)

        if response.status_code == 200:
            data = response.json()
            self.access_token = data["access_token"]
            self.refresh_token = data["refresh_token"]
            self.headers["Authorization"] = f"Bearer {self.access_token}"
            return True
        logger.error(f"Token refresh failed: {response.status_code} {response.text}")
        return False

    def add_host_header(self, url):
        """Add Host header to requests if needed."""
        # Extract hostname from URL to set the Host header
        from urllib.parse import urlparse

        parsed_url = urlparse(url)
        hostname = parsed_url.netloc
        self.headers["Host"] = hostname
        return url


@app.command()
def main(
    server: str = typer.Option("http://localhost:8000", "--server", "-s", help="API server URL"),
    email: Optional[str] = typer.Option(None, "--email", "-e", help="Email for authentication"),
    password: Optional[str] = typer.Option(None, "--password", "-p", help="Password for authentication"),
    guest: bool = typer.Option(False, "--guest", "-g", help="Use guest mode (no login required)"),
    origin: str = typer.Option("http://localhost:8081", "--origin", "-o", help="Origin header for CORS validation"),
    mobile: bool = typer.Option(False, "--mobile", "-m", help="Use mobile header to bypass CORS checks"),
    json_mode: bool = typer.Option(False, "--json", "-j", help="Display raw JSON responses"),
    show_thread: bool = typer.Option(False, "--show-thread", "-t", help="Show the full thread JSON after sending a message"),
    input: Optional[str] = typer.Option(
        None, "--input", "-i", help="Input to send to the API. If not provided, starts interactive mode."
    ),
    log_level: str = typer.Option(
        "INFO", "--log-level", "-l", help="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)", case_sensitive=False
    ),
):
    """
    Command-line client for Ansari API.

    If input is provided, process it and exit.
    If no input is provided, start interactive mode.

    Use --guest for quick access without creating an account.
    Use --mobile to bypass CORS checks for development.
    Use --show-thread to display the thread JSON data after each message.
    """
    # Configure logging
    numeric_level = getattr(logging, log_level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f"Invalid log level: {log_level}")
    logging.basicConfig(level=numeric_level)

    # Initialize API client
    client = AnsariApiClient(server, email, password, origin=origin, mobile_header=mobile, json_mode=json_mode)

    if guest:
        # Use guest mode - register a temporary account
        console.print("Starting in guest mode...")
        console.print("Registering temporary guest account...")
        if not client.register_guest():
            console.print("[red]Failed to create guest account. Please try again later.[/red]")
            return
        console.print(f"[green]Guest account created and logged in as {client.email}[/green]")
    else:
        # Normal login flow
        # Get credentials if not provided
        if not email:
            client.email = Prompt.ask("Email")
        if not password:
            client.password = Prompt.ask("Password", password=True)

        # Login
        console.print("Logging in...")
        if not client.login():
            console.print("[red]Login failed. Please check your credentials.[/red]")
            return

        console.print(f"[green]Login successful! Welcome, {client.user_info['first_name']}.[/green]")

    # Create a thread
    console.print("Creating conversation thread...")
    thread_data = client.create_thread()
    if not thread_data:
        console.print("[red]Failed to create thread.[/red]")
        return

    thread_id = thread_data["thread_id"]
    console.print(f"[cyan]Thread created with ID: {thread_id}[/cyan]")

    if input:
        # Send single message and display response
        console.print(f"[bold]You:[/bold] {input}")
        console.print("[bold]Ansari:[/bold] ", end="")

        response = client.send_message(thread_id, input)
        if response:
            if client.json_mode:
                # In JSON mode, display the raw JSON response
                import json

                response_text = response.text
                try:
                    # Try to parse and pretty-print the JSON
                    json_data = json.loads(response_text)
                    formatted_json = json.dumps(json_data, indent=2)
                    console.print_json(formatted_json)
                except json.JSONDecodeError:
                    # If not valid JSON, just print the raw response
                    console.print(response_text)
            else:
                # Normal streaming text mode
                buffer = b""
                for chunk in response.iter_content(chunk_size=4):
                    if chunk:
                        buffer += chunk
                        try:
                            decoded = buffer.decode("utf-8")
                            print(decoded, end="", flush=True)
                            buffer = b""
                        except UnicodeDecodeError:
                            # Continue buffering until we have a complete UTF-8 character
                            continue

                # Decode any remaining bytes in the buffer
                if buffer:
                    try:
                        print(buffer.decode("utf-8", errors="replace"), end="", flush=True)
                    except Exception as e:
                        logger.error(f"Error decoding final buffer: {e}")

                print()

            # If show_thread is enabled, get and display the thread JSON
            if show_thread:
                console.print("\n[bold yellow]Thread JSON:[/bold yellow]")
                thread_data = client.get_thread(thread_id)
                if thread_data:
                    import json

                    formatted_json = json.dumps(thread_data, indent=2)
                    console.print_json(formatted_json)
                else:
                    console.print("[red]Failed to get thread data.[/red]")
        else:
            console.print("[red]Failed to get response.[/red]")
    else:
        # Interactive mode
        console.print("[yellow]Starting interactive mode. Type 'exit' to quit.[/yellow]")
        while True:
            user_input = Prompt.ask("\n[bold]You[/bold]")
            if user_input.lower() in ("exit", "quit"):
                break

            response = client.send_message(thread_id, user_input)
            if response:
                console.print("[bold]Ansari:[/bold] ", end="")

                if client.json_mode:
                    # In JSON mode, display the raw JSON response
                    import json

                    response_text = response.text
                    try:
                        # Try to parse and pretty-print the JSON
                        json_data = json.loads(response_text)
                        formatted_json = json.dumps(json_data, indent=2)
                        console.print_json(formatted_json)
                    except json.JSONDecodeError:
                        # If not valid JSON, just print the raw response
                        console.print(response_text)
                else:
                    # Normal streaming text mode
                    buffer = b""
                    for chunk in response.iter_content(chunk_size=4):
                        if chunk:
                            buffer += chunk
                            try:
                                decoded = buffer.decode("utf-8")
                                print(decoded, end="", flush=True)
                                buffer = b""
                            except UnicodeDecodeError:
                                # Continue buffering until we have a complete UTF-8 character
                                continue

                    # Decode any remaining bytes in the buffer
                    if buffer:
                        try:
                            print(buffer.decode("utf-8", errors="replace"), end="", flush=True)
                        except Exception as e:
                            logger.error(f"Error decoding final buffer: {e}")
                    print()

                # If show_thread is enabled, get and display the thread JSON
                if show_thread:
                    console.print("\n[bold yellow]Thread JSON:[/bold yellow]")
                    thread_data = client.get_thread(thread_id)
                    if thread_data:
                        import json

                        formatted_json = json.dumps(thread_data, indent=2)
                        console.print_json(formatted_json)
                    else:
                        console.print("[red]Failed to get thread data.[/red]")
            else:
                console.print("[red]Failed to get response.[/red]")
                # Try to refresh token and retry
                if client.refresh_auth_token():
                    console.print("[yellow]Auth token refreshed. Retrying...[/yellow]")
                    response = client.send_message(thread_id, user_input)
                    if response:
                        console.print("[bold]Ansari:[/bold] ", end="")

                        if client.json_mode:
                            # In JSON mode, display the raw JSON response
                            import json

                            response_text = response.text
                            try:
                                # Try to parse and pretty-print the JSON
                                json_data = json.loads(response_text)
                                formatted_json = json.dumps(json_data, indent=2)
                                console.print_json(formatted_json)
                            except json.JSONDecodeError:
                                # If not valid JSON, just print the raw response
                                console.print(response_text)
                        else:
                            # Normal streaming text mode
                            buffer = b""
                            for chunk in response.iter_content(chunk_size=4):
                                if chunk:
                                    buffer += chunk
                                    try:
                                        decoded = buffer.decode("utf-8")
                                        print(decoded, end="", flush=True)
                                        buffer = b""
                                    except UnicodeDecodeError:
                                        # Continue buffering until we have a complete UTF-8 character
                                        continue

                            # Decode any remaining bytes in the buffer
                            if buffer:
                                try:
                                    print(buffer.decode("utf-8", errors="replace"), end="", flush=True)
                                except Exception as e:
                                    logger.error(f"Error decoding final buffer: {e}")
                            print()

                        # If show_thread is enabled, get and display the thread JSON
                        if show_thread:
                            console.print("\n[bold yellow]Thread JSON:[/bold yellow]")
                            thread_data = client.get_thread(thread_id)
                            if thread_data:
                                import json

                                formatted_json = json.dumps(thread_data, indent=2)
                                console.print_json(formatted_json)
                            else:
                                console.print("[red]Failed to get thread data.[/red]")
                    else:
                        console.print("[red]Request failed after token refresh.[/red]")


if __name__ == "__main__":
    logger.debug("Starting the Ansari API client...")
    app()
