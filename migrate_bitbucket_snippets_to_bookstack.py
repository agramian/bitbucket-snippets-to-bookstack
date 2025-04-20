# python
import requests
import base64
import json
import argparse
import sys
import time
from urllib.parse import urljoin, quote

# --- Configuration ---
BITBUCKET_API_BASE = "https://api.bitbucket.org/2.0/"
BOOKSTACK_API_BASE = None # Provided via arguments

# --- Helper Functions ---

def make_request(method, url, headers, **kwargs):
    """Makes an HTTP request and handles basic errors."""
    # Add expect_json parameter to control decoding
    expect_json = kwargs.pop('expect_json', True)
    # Add caller_info parameter to control special handling
    caller_info = kwargs.pop('caller_info', '')
    try:
        response = requests.request(method, url, headers=headers, timeout=30, **kwargs)
        # Allow 404 specifically for get_snippet_revision_content as it means file didn't exist
        if response.status_code == 404 and "get_snippet_revision_content" in caller_info:
            print(f"Info: Received 404 for {url}, likely file not present in this revision.")
            return None # Indicate file not found for this revision

        response.raise_for_status() # Raise HTTPError for other bad responses (4xx or 5xx)

        if response.status_code == 204:
            return None # No content

        # Only decode JSON if expected
        if expect_json and 'application/json' in response.headers.get('Content-Type', ''):
            try:
                return response.json()
            except json.JSONDecodeError as e:
                print(f"Error decoding JSON response from {url}: {e}", file=sys.stderr)
                print(f"Response text: {response.text}", file=sys.stderr)
                return None # Indicate JSON decode failure
        else:
            # Return raw content if not JSON (e.g., getting snippet file content)
            return response.text
    except requests.exceptions.RequestException as e:
        print(f"Error making {method} request to {url}: {e}", file=sys.stderr)
        if hasattr(e, 'response') and e.response is not None:
            try:
                # Only print body for non-404 errors in this context or if needed
                if not (response.status_code == 404 and "get_snippet_revision_content" in kwargs.get("caller_info", "")):
                    print(f"Response body: {e.response.text}", file=sys.stderr)
            except Exception:
                print("Could not decode error response body.", file=sys.stderr)
        return None


def get_paginated_results(url, headers):
    """Retrieves all items from a paginated API endpoint."""
    results = []
    next_url = url
    while next_url:
        # Ensure JSON is expected for pagination metadata
        data = make_request("GET", next_url, headers=headers, expect_json=True)
        if data is None: # Handle make_request returning None on error
            print(f"Error: Failed to fetch or parse paginated data from {next_url}", file=sys.stderr)
            return None # Propagate error

        if not isinstance(data, dict) or 'values' not in data:
            print(f"Warning: Unexpected data structure in response from {next_url}. Response: {data}", file=sys.stderr)
            break # Stop pagination if structure is wrong

        results.extend(data['values'])
        next_url = data.get('next')
        # time.sleep(0.1) # Optional delay
    return results

# --- Bitbucket API Functions ---

def get_bitbucket_snippets(workspace, headers, specific_snippet_id=None):
    """Gets snippets for a workspace, or a single specific snippet if ID is provided."""
    if specific_snippet_id:
        # Always expect JSON for snippet metadata
        url = urljoin(BITBUCKET_API_BASE, f"snippets/{quote(workspace)}/{quote(specific_snippet_id)}")
        print(f"Fetching specific snippet {specific_snippet_id} from {url}...")
        snippet_data = make_request("GET", url, headers=headers, expect_json=True)
        return [snippet_data] if snippet_data else [] # Return as list
    else:
        url = urljoin(BITBUCKET_API_BASE, f"snippets/{quote(workspace)}")
        print(f"Fetching all snippets from {url}...")
        snippets = get_paginated_results(url, headers)
        if snippets is None: # Handle error from get_paginated_results
            return None
        print(f"Found {len(snippets)} snippets.")
        return snippets

def get_snippet_details(workspace, snippet_id, headers):
    """Gets details for a single snippet, including the list of current files."""
    # Always expect JSON for snippet metadata
    url = urljoin(BITBUCKET_API_BASE, f"snippets/{quote(workspace)}/{quote(snippet_id)}")
    print(f"Fetching details for snippet {snippet_id}...")
    details = make_request("GET", url, headers=headers, expect_json=True)
    return details


def get_snippet_commits(workspace, snippet_id, headers):
    """Gets commit history for a specific snippet, oldest first."""
    # Always expect JSON for commit metadata
    url = urljoin(BITBUCKET_API_BASE, f"snippets/{quote(workspace)}/{quote(snippet_id)}/commits")
    print(f"Fetching commits for snippet {snippet_id}...")
    commits = get_paginated_results(url, headers)
    if commits is None: # Handle error from get_paginated_results
        return None
    print(f"Found {len(commits)} commits for snippet {snippet_id}.")
    # Reverse to get oldest first for sequential application
    return list(reversed(commits))

def get_snippet_revision_content(workspace, snippet_id, commit_hash, file_path, headers):
    """Gets the raw content of a specific file within a snippet revision."""
    # Don't expect JSON for raw file content
    # Pass caller_info to allow specific 404 handling in make_request
    url = urljoin(BITBUCKET_API_BASE, f"snippets/{quote(workspace)}/{quote(snippet_id)}/{commit_hash}/files/{quote(file_path)}")
    print(f"Fetching content for snippet {snippet_id}, commit {commit_hash}, file '{file_path}'...")
    content = make_request("GET", url, headers=headers, expect_json=False, caller_info="get_snippet_revision_content")

    # content will be None if 404 occurred (handled in make_request) or other error happened
    if content is None:
        return None # Indicate failure/not found

    # Ensure content is a string
    if not isinstance(content, str):
        try:
            content = content.decode('utf-8', errors='replace') # Replace errors instead of failing
        except AttributeError:
            print(f"Warning: Content for {file_path} in commit {commit_hash} is not bytes or string. Using empty string.", file=sys.stderr)
            return "" # Fallback
    return content


# --- Bookstack API Functions ---

def find_bookstack_book(name, headers):
    """Finds a Bookstack book by its exact name."""
    # Expect JSON response
    book_api_url = urljoin(BOOKSTACK_API_BASE, "api/books")
    params = {'filter[name]': name}
    print(f"Searching for book titled '{name}'...")
    response = make_request("GET", book_api_url, headers=headers, params=params, expect_json=True)

    if response and 'data' in response and response['data']:
        # Assuming the first result with the exact name is the one we want
        for book in response['data']:
            if book.get('name') == name:
                print(f"Found existing book ID: {book['id']}")
                return book
    print(f"Book '{name}' not found.")
    return None

def create_bookstack_book(name, headers):
    """Creates a new book in Bookstack."""
    # Expect JSON response
    book_api_url = urljoin(BOOKSTACK_API_BASE, "api/books")
    payload = {
        "name": name,
        "description": "Imported from Bitbucket Snippet", # Optional description
        "tags": [{"name": "Bitbucket Snippet Import", "value": name}] # Optional tag
    }
    print(f"Creating new book '{name}'...")
    return make_request("POST", book_api_url, headers=headers, json=payload, expect_json=True)

def find_bookstack_page(book_id, page_name, headers):
    """Finds a Bookstack page by name within a specific book."""
    # Expect JSON response
    page_api_url = urljoin(BOOKSTACK_API_BASE, "api/pages")
    pages_found = []
    offset = 0
    count = 100 # Fetch pages in batches

    print(f"Searching for page named '{page_name}' in book ID {book_id}...")

    while True:
        params = {'book_id': book_id, 'count': count, 'offset': offset}
        response = make_request("GET", page_api_url, headers=headers, params=params, expect_json=True)

        if response is None: # Handle request error
            print(f"Error: Failed to list pages for book {book_id}", file=sys.stderr)
            return None # Indicate error

        if not response or 'data' not in response:
            print(f"Warning: Could not parse page data for book {book_id}", file=sys.stderr)
            break

        current_pages = response['data']
        if not current_pages:
            break # No more pages

        for page in current_pages:
            if page.get('name') == page_name:
                # Found the page
                print(f"Found existing page ID: {page['id']}")
                return page

        if response.get('total', 0) <= offset + len(current_pages):
            break # Reached the end based on total count

        offset += len(current_pages) # Increment offset correctly

    print(f"Page '{page_name}' not found in book {book_id}.")
    return None


def create_bookstack_page(book_id, page_name, content, headers, commit_info="Initial import"):
    """Creates a new page in Bookstack."""
    # Expect JSON response
    page_api_url = urljoin(BOOKSTACK_API_BASE, "api/pages")
    payload = {
        "book_id": book_id,
        "name": page_name,
        "markdown": content, # Use markdown field
        "tags": [{"name": "Snippet File", "value": page_name}] # Optional tag
    }
    print(f"Creating new page '{page_name}' in book {book_id} ({commit_info})...")
    return make_request("POST", page_api_url, headers=headers, json=payload, expect_json=True)

def update_bookstack_page(page_id, content, headers, commit_info=""):
    """Updates an existing page in Bookstack, creating a revision."""
    # Expect JSON response
    page_api_url = urljoin(BOOKSTACK_API_BASE, f"api/pages/{page_id}")
    payload = {
        "markdown": content,
        "summary": f"Update from Bitbucket ({commit_info})" # Revision summary
    }
    print(f"Updating page ID {page_id} ({commit_info})...")
    return make_request("PUT", page_api_url, headers=headers, json=payload, expect_json=True)

# --- Main Execution ---

def main():
    parser = argparse.ArgumentParser(description="Migrate Bitbucket Snippets (as Books) and their files (as Pages) to Bookstack with history.")
    parser.add_argument("--bb-user", required=True, help="Bitbucket username.")
    parser.add_argument("--bb-app-password", required=True, help="Bitbucket app password.")
    parser.add_argument("--bb-workspace", help="Bitbucket workspace ID. Defaults to bb-user if not specified.")
    parser.add_argument("--bs-url", required=True, help="Base URL of your Bookstack instance (e.g., https://bookstack.example.com).")
    parser.add_argument("--bs-token-id", required=True, help="Bookstack API Token ID.")
    parser.add_argument("--bs-token-secret", required=True, help="Bookstack API Token Secret.")
    # No longer need --bs-book-id
    parser.add_argument("--skip-existing-books", action="store_true", help="Skip snippets entirely if a Book with the same title already exists.")
    parser.add_argument("--skip-existing-pages", action="store_true", help="Skip creating/updating pages if they already exist in the target book (use with caution, prevents history update).")
    parser.add_argument("--test-snippet-id", help="Only process the snippet with this specific ID for testing.")


    args = parser.parse_args()

    bitbucket_workspace = args.bb_workspace if args.bb_workspace else args.bb_user
    print(f"Using Bitbucket Workspace: {bitbucket_workspace}")

    global BOOKSTACK_API_BASE
    BOOKSTACK_API_BASE = args.bs_url.rstrip('/') # Ensure no trailing slash

    # --- Prepare Headers ---
    bb_credentials = f"{args.bb_user}:{args.bb_app_password}"
    bb_encoded_credentials = base64.b64encode(bb_credentials.encode()).decode()
    bb_headers = {
        "Authorization": f"Basic {bb_encoded_credentials}",
        "Accept": "application/json"
    }

    bs_headers = {
        "Authorization": f"Token {args.bs_token_id}:{args.bs_token_secret}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

    # --- Get Snippets (potentially just one for testing) ---
    snippets = get_bitbucket_snippets(bitbucket_workspace, bb_headers, args.test_snippet_id)
    if snippets is None:
        print("Error: Failed to fetch Bitbucket snippets. Exiting.", file=sys.stderr)
        sys.exit(1)
    if not snippets:
        print("No snippets found matching the criteria.")
        sys.exit(0)


    # --- Process Each Snippet (-> Book) ---
    for snippet_summary in snippets:
        if not snippet_summary or 'id' not in snippet_summary:
            print(f"Warning: Invalid snippet data encountered: {snippet_summary}. Skipping.", file=sys.stderr)
            continue

        snippet_id = str(snippet_summary['id'])
        snippet_title = snippet_summary.get('title', f"Untitled Snippet {snippet_id}")
        print(f"\n--- Processing Snippet: '{snippet_title}' (ID: {snippet_id}) ---")

        # --- Find or Create Bookstack Book ---
        target_book = find_bookstack_book(snippet_title, bs_headers)
        book_id = None
        if target_book:
            if args.skip_existing_books:
                print(f"Skipping snippet '{snippet_title}' as --skip-existing-books is set and book exists (ID: {target_book.get('id')}).")
                continue
            else:
                print(f"Found existing book '{snippet_title}' (ID: {target_book.get('id')}). Will add/update pages within it.")
                book_id = target_book.get('id')
        else:
            created_book = create_bookstack_book(snippet_title, bs_headers)
            if created_book and 'id' in created_book:
                book_id = created_book['id']
                print(f"Successfully created book ID: {book_id}")
            else:
                print(f"Error: Failed to create book for snippet '{snippet_title}'. Skipping this snippet.", file=sys.stderr)
                continue # Skip to the next snippet

        if not book_id:
            print(f"Error: Could not determine Book ID for snippet '{snippet_title}'. Skipping.", file=sys.stderr)
            continue

        # --- Get Snippet Details (for file list) and Commits ---
        snippet_details = get_snippet_details(bitbucket_workspace, snippet_id, bb_headers)
        if not snippet_details or 'files' not in snippet_details:
            print(f"Warning: Could not get file list for snippet {snippet_id}. Skipping.", file=sys.stderr)
            continue

        current_files = snippet_details['files'] # This is a dictionary: {"filename": {"links": {"self": ...}}}
        if not current_files:
            print(f"Info: Snippet {snippet_id} ('{snippet_title}') appears to have no files. Skipping.")
            continue

        commits = get_snippet_commits(bitbucket_workspace, snippet_id, bb_headers)
        if commits is None:
            print(f"Error: Failed to fetch commits for snippet {snippet_id}. Skipping files within this snippet.", file=sys.stderr)
            continue
        if not commits:
            print(f"Warning: No commit history found for snippet {snippet_id}. Pages will be created based on current content only.", file=sys.stderr)
            # We can still proceed to create pages based on the *current* state if commits are empty
            # Let's synthesize a 'current' state commit info for this case
            commits = [{"hash": "HEAD", "date": snippet_details.get("updated_on", "N/A"), "message": "Current state", "author": {"raw": "N/A"}}]


        # --- Process Each File (-> Page) ---
        for filename in current_files.keys():
            print(f"\n  -- Processing File (Page): '{filename}' --")
            target_page = find_bookstack_page(book_id, filename, bs_headers)
            page_id = None
            page_created_in_this_run = False

            if target_page:
                if args.skip_existing_pages:
                    print(f"  Skipping page '{filename}' as --skip-existing-pages is set and page exists (ID: {target_page.get('id')}).")
                    continue # Skip to the next file
                else:
                    print(f"  Found existing page '{filename}' (ID: {target_page.get('id')}). Will update with history.")
                    page_id = target_page.get('id')
            else:
                # Page needs to be created. Will happen during first successful commit fetch.
                pass


            # --- Apply Commits to this File/Page ---
            processed_first_commit_for_page = False
            previous_page_content = None
            for i, commit in enumerate(commits):
                commit_hash = commit['hash']
                commit_date = commit.get('date', 'Unknown Date')
                commit_message = commit.get('message', 'No message')
                commit_author = commit.get('author', {}).get('raw', 'Unknown author')
                commit_info = f"Commit {commit_hash[:7]} by {commit_author} on {commit_date}. Msg: {commit_message}"

                print(f"    Applying commit {i+1}/{len(commits)}: {commit_hash[:7]}...")

                # Attempt to get content for *this specific file* at *this specific commit*
                content = get_snippet_revision_content(bitbucket_workspace, snippet_id, commit_hash, filename, bb_headers)

                if content is None:
                    # File likely didn't exist or error occurred (already logged in make_request/get_content)
                    print(f"    Skipping revision for commit {commit_hash[:7]} (file content not found/retrieved).")
                    continue # Skip to the next commit for this file

                # Prepend Bitbucket info to the content
                header_info = f"\n\n"
                page_content = header_info + content

                # Now, either create or update the Bookstack page
                if not page_id and not page_created_in_this_run:
                    # First successful content fetch for this file, and page doesn't exist yet. Create it.
                    created_page = create_bookstack_page(book_id, filename, page_content, bs_headers, commit_info)
                    if created_page and 'id' in created_page:
                        page_id = created_page['id']
                        page_created_in_this_run = True # Mark as created
                        processed_first_commit_for_page = True # Don't update immediately after creation
                        print(f"  Successfully created page ID: {page_id} for file '{filename}'")
                    else:
                        print(f"  Error: Failed to create page for file '{filename}'. Skipping remaining commits for this file.", file=sys.stderr)
                        break # Stop processing commits for this file
                elif page_id and not processed_first_commit_for_page :
                    # Page exists (or was just created), maybe update it
                    if previous_page_content != page_content:
                        # The content change so update the page
                        updated_page = update_bookstack_page(page_id, page_content, bs_headers, commit_info)
                        if not updated_page:
                            print(f"  Error: Failed to update page ID {page_id} for commit {commit_hash[:7]}. Continuing...", file=sys.stderr)
                    else:
                        print(f"  The page content did not change on page ID {page_id} for commit {commit_hash[:7]}. Skipping...")
                elif page_id and processed_first_commit_for_page:
                    # If we just created the page on this commit, reset the flag so the *next* commit updates it
                    processed_first_commit_for_page = False

                # Store the previous page content for comparison on the next iteration
                previous_page_content = page_content

                # Optional: Add a small delay
                # time.sleep(0.2)

            if not page_id and not page_created_in_this_run:
                print(f"  Warning: No content could be retrieved for file '{filename}' from any commit. Page was not created.", file=sys.stderr)


    print("\n--- Migration Complete ---")

if __name__ == "__main__":
    main()
