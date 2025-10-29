import requests
import json
import time
from pathlib import Path
import os
from dotenv import load_dotenv


class NaukriAPIClient:
    """
    Client for Naukri.com APIs.
    Handles login, cookies, and authenticated requests.
    Uses JSON files for credentials and cookies.
    """

    def __init__(
        self,
        username: str = None,
        password: str = None,
        base_url="https://www.naukri.com",
        cookie_file="cookies.json",
    ):
        
        load_dotenv()  # Load from .env if exists

        # Use priority: CLI args → env vars → None
        self.username = username or os.getenv("NAUKRI_USERNAME")
        self.password = password or os.getenv("NAUKRI_PASSWORD")

        if not self.username or not self.password:
            raise ValueError("❌ Missing credentials. Please set .env or use --user and --password flags.")


        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.cookie_file = Path(cookie_file)

        # Default headers required by Naukri
        self.headers = {
            "appid": "103",
            "systemid": "jobseeker",
            "Content-Type": "application/json",
        }

        self._load_cookies()

    # ----------------------------------------------------------------
    # AUTHENTICATION METHODS
    # ----------------------------------------------------------------
    def login(self):
        """Login to Naukri and store cookies."""
        login_url = f"{self.base_url}/central-login-services/v1/login"
        payload = {"username": self.username, "password": self.password}

        print("Logging in...")
        resp = self.session.post(login_url, headers=self.headers, json=payload)
        resp.raise_for_status()
        data = resp.json()

        if "cookies" not in data:
            raise ValueError("❌ Login response does not contain cookies")

        self._set_cookies_from_json(data["cookies"])
        self._save_cookies()
        print("Login successful. Cookies saved.")

    def logout(self):
        """Clear cookies and session."""
        self.session.cookies.clear()
        if self.cookie_file.exists():
            self.cookie_file.unlink()
        print("Logged out and cleared cookies.")

    # ----------------------------------------------------------------
    # BUSINESS / FEATURE METHODS
    # ----------------------------------------------------------------
    def get_profile(self):
        """
        Fetch logged-in user's profile details.
        Returns dict if successful, else None.
        """

        url = f"{self.base_url}/cloudgateway-mynaukri/resman-aggregator-services/v2/users/self?expand_level=4"

        # Refresh cookies if expired
        if self._is_cookie_expired():
            self.login()

        try:
            resp = self.session.get(url, headers=self.headers)
            if resp.status_code == 401:
                print("Unauthorized. Re-logging in...")
                self.login()
                resp = self.session.get(url, headers=self.headers)

            if resp.status_code == 200:
                return resp.json()
            else:
                print(f"Failed to fetch profile: {resp.status_code}")
                return None
        except Exception as e:
            print(f"Exception while fetching profile: {e}")
            return None
        
    def upload_resume(self, file_path):
        """
        Uploads a file (e.g., resume) to Naukri's file upload API.
        Returns only the file key (e.g. 'UR54EQmIiGvBMt').

        Args:
            file_path (str): Path to the file on disk.
        Returns:
            str | None: The file key if upload successful, else None.
        """

        url = "https://filevalidation.naukri.com/file"

        # Static form fields (as per your configuration)
        data = {
            "formKey": "F51f8e7e54e205",
            "fileName": Path(file_path).name,
            "uploadCallback": "true"
        }

        # Required headers for this upload API
        headers = {
            "appid": "105",
            "systemid": "fileupload",
        }

        try:
            with open(file_path, "rb") as f:
                files = {"file": (Path(file_path).name, f)}

                print(f"Uploading file: {file_path}")
                response = self.session.post(url, headers=headers, files=files, data=data)
                response.raise_for_status()

                # Expect JSON like:
                # { "UR54EQmIiGvBMt": { "url": "//filevalidation.naukri.com/file/download?..."} }
                resp_json = response.json()

                if not isinstance(resp_json, dict) or not resp_json:
                    print("Unexpected response structure.")
                    return None

                file_key = next(iter(resp_json.keys()))
                print(f"Upload successful")

                profile_data = self.get_profile()
                
                if not profile_data['profile'][0]['profileId']:
                    print("Profile ID missing in response.")
                    return False
                
                return self.update_resume(file_key=file_key, profile_id=profile_data['profile'][0]['profileId'])

        except FileNotFoundError:
            print(f"File not found: {file_path}")
            return None
        except requests.RequestException as e:
            print(f"Upload failed: {e}")
            return None
    
    def update_resume(self, file_key, profile_id):
        """
        Updates the user's resume using an already uploaded file.

        Args:
            file_key (str): The fileKey obtained from the file upload API.
            profile_id (str): The user's profile ID.

        Returns:
            bool: True if resume update is successful, else False.
        """

        url = f"{self.base_url}/cloudgateway-mynaukri/resman-aggregator-services/v0/users/self/profiles/{profile_id}/advResume"

        payload = {
            "textCV": {
                "formKey": "F51f8e7e54e205",
                "fileKey": file_key,
                "textCvContent": None
            }
        }

        headers = {
            "appid": "135",
            "systemid": "135",
            "Content-Type": "application/json",
            "x-http-method-override": "PUT",
            "x-requested-with": "XMLHttpRequest"
        }

        try:
            print(f"Updating resume for profile: {profile_id}")
            response = self.session.post(url, headers=headers, json=payload)
            response.raise_for_status()

            if response.status_code == 200:
                print("Resume updated successfully.")
                return True
            else:
                print(f"Resume update failed: {response.status_code}")
                return False

        except requests.RequestException as e:
            print(f"Resume update error: {e}")
            return False
        
    def refresh_resume_headline(self):
        """
        Refreshes the user's resume headline by temporarily adding and removing
        a '.' at the end of the current headline. This triggers a 'resume refresh'
        on Naukri.

        Returns:
            bool: True if refresh successful, else False.
        """

        # Step 1️⃣ - Get profile info to extract profileId and current headline
        profile_data = self.get_profile()
        profile_list = profile_data.get("profile", [])
        if not profile_list:
            print("⚠️ No profile data found.")
            return False

        profile = profile_list[0]
        profile_id = profile.get("profileId")
        current_headline = profile.get("resumeHeadline")

        if not profile_id or not current_headline:
            print("⚠️ Missing profileId or resumeHeadline in response.")
            return False

        print(f"📝 Current headline: {current_headline}")

        url = f"{self.base_url}/cloudgateway-mynaukri/resman-aggregator-services/v1/users/self/fullprofiles"
        headers = {
            "appid": "135",
            "systemid": "Naukri",
            "Content-Type": "application/json",
            "x-http-method-override": "PUT",
            "x-requested-with": "XMLHttpRequest"
        }

        # Step 2️⃣ - Add '.' to the end and update
        headline_with_dot = current_headline.rstrip(".") + "."
        payload_add = {
            "profile": {"resumeHeadline": headline_with_dot},
            "profileId": profile_id
        }

        try:
            print("🔄 Step 1: Adding '.' to refresh headline...")
            resp_add = self.session.post(url, headers=headers, json=payload_add)
            resp_add.raise_for_status()
            if resp_add.status_code != 200:
                print(f"⚠️ Failed to update headline (add '.'). Status: {resp_add.status_code}")
                return False

            # Step 3️⃣ - Remove '.' and revert to original headline
            payload_revert = {
                "profile": {"resumeHeadline": current_headline},
                "profileId": profile_id
            }

            print("🔁 Step 2: Reverting headline to original...")
            resp_revert = self.session.post(url, headers=headers, json=payload_revert)
            resp_revert.raise_for_status()
            if resp_revert.status_code == 200:
                print("✅ Resume headline refreshed successfully.")
                return True
            else:
                print(f"⚠️ Failed to revert headline. Status: {resp_revert.status_code}")
                return False

        except requests.RequestException as e:
            print(f"❌ Error refreshing headline: {e}")
            return False
                
    # ----------------------------------------------------------------
    # INTERNAL HELPERS
    # ----------------------------------------------------------------

    def _set_cookies_from_json(self, cookie_list):
        """Add cookies from API response JSON into the session."""
        for c in cookie_list:
            if "name" in c and "value" in c:
                self.session.cookies.set(
                    name=c["name"],
                    value=c["value"],
                    domain=c.get("domain", ".naukri.com")
                )

    def _save_cookies(self):
        """Save cookies to a local JSON file."""
        cookies_dict = []
        for c in self.session.cookies:
            cookies_dict.append({
                "name": c.name,
                "value": c.value,
                "domain": c.domain,
                "expiry": int(time.time()) + 3600  # fallback 1-hour expiry if not provided
            })

        with open(self.cookie_file, "w") as f:
            json.dump(cookies_dict, f, indent=2)

        print(f"Cookies saved to {self.cookie_file}")

    def _load_cookies(self):
        """Load cookies from local JSON file if present."""
        if not self.cookie_file.exists():
            return
        try:
            with open(self.cookie_file, "r") as f:
                cookies_dict = json.load(f)
            self._set_cookies_from_json(cookies_dict)
            print(f"Loaded cookies from {self.cookie_file}")
        except Exception as e:
            print(f"Could not load cookies: {e}")

    def _is_cookie_expired(self):
        """Check if saved cookies are expired."""
        if not self.cookie_file.exists():
            return True
        try:
            with open(self.cookie_file, "r") as f:
                cookies = json.load(f)
            now = int(time.time())
            for c in cookies:
                exp = c.get("expiry", 0)
                if exp and exp < now:
                    print(f"Cookie {c['name']} expired at {exp}")
                    return True
            return False
        except Exception as e:
            print(f"Could not check cookie expiry: {e}")
            return True


# ----------------------------------------------------------------
# Example usage
# ----------------------------------------------------------------
if __name__ == "__main__":
    client = NaukriAPIClient()

    # Make sure logged in
    if client._is_cookie_expired() or not client.session.cookies:
        client.login()

