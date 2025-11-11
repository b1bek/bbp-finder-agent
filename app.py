import io
import time
import streamlit as st
from openai import OpenAI

# Remove environment variable support; use dashboard (session state) instead
# Initialize session state defaults
if "OPENAI_API_KEY" not in st.session_state:
    st.session_state["OPENAI_API_KEY"] = ""
if "OPENAI_MODEL" not in st.session_state:
    st.session_state["OPENAI_MODEL"] = "gpt-4.1-mini"
if "ACTIVE_VECTOR_STORE_ID" not in st.session_state:
    st.session_state["ACTIVE_VECTOR_STORE_ID"] = None

# Initialize OpenAI client from dashboard-provided API key
client = OpenAI(api_key=st.session_state.get("OPENAI_API_KEY")) if st.session_state.get("OPENAI_API_KEY") else None

# Default model used for Responses API calls
MODEL_NAME = st.session_state.get("OPENAI_MODEL", "gpt-4.1-mini")

# Helper to resolve the active vector store id (only session state)
def get_active_vector_store_id():
    return st.session_state.get("ACTIVE_VECTOR_STORE_ID")

# --- Streamlit UI ---
st.set_page_config(page_title="Bug Bounty Program Finder", page_icon="🔎", layout="centered")
st.title("Bug Bounty Program Finder")
st.write("Enter email, org name, domain/URLs, or any info to see if a bug bounty program (BBP) exists.")

user_text = st.text_area(
    "Input",
    placeholder="e.g., example.com, security@example.com, Org Name",
    height=150,
)

if st.button("Find Program"):
    if not user_text.strip():
        st.warning("Please provide some input (domain, email, org name, etc.).")
    elif not client:
        st.error("OpenAI API key is not set. Please set it in the sidebar under Settings.")
    elif not get_active_vector_store_id():
        st.error("No active vector store set. Create one or set an ID in the 'Manage Knowledge Base' section.")
    else:
        with st.spinner("Searching for Bug Bounty Program..."):
            try:
                # Build a concise instruction leveraging File Search tool
                prompt = (
                    # "You're assigned a task to determine whether a bug bounty program exists for the given input. "
                    # "Use the file_search tool on the provided vector store to verify. "
                    # "Respond strictly only in JSON object 'Found' (Yes/No), 'Source', 'Rewards' (Yes/No), and 'Program Url'. "
                    # f"Input: {user_text.strip()}"
                    "You’re assigned a task to determine whether a bug bounty program exists for the given input. "
                    "Use the file_search tool on the provided vector store to verify. "
                    "Respond strictly in a **single JSON object only**, with no explanations or extra text. "
                    "Fields required: 'Found' (Yes/No), 'Source', 'Rewards' (Yes/No), 'Program Url'. "
                    f"Input: {user_text.strip()}"

                )

                response = client.responses.create(
                    model=MODEL_NAME,
                    input=prompt,
                    tools=[{
                        "type": "file_search",
                        "vector_store_ids": [get_active_vector_store_id()]
                    }]
                )

                # Extract output text (and optional citations) from the response
                output_text = ""
                citations = []
                try:
                    for item in (response.output or []):
                        if getattr(item, "type", None) == "message":
                            for content in (item.content or []):
                                if getattr(content, "type", None) == "output_text":
                                    output_text += content.text or ""
                                    anns = getattr(content, "annotations", None) or []
                                    for ann in anns:
                                        if getattr(ann, "type", None) == "file_citation":
                                            citations.append({
                                                "file_id": getattr(ann, "file_id", ""),
                                                "filename": getattr(ann, "filename", "")
                                            })
                except Exception:
                    # Fallback: stringify full response if structured parsing fails
                    output_text = str(response)

                if output_text:
                    st.success("Result")
                    # Show as JSON/code block for readability
                    st.code(output_text, language="json")
                    if citations:
                        st.caption("Citations:")
                        for c in citations:
                            fn = c.get("filename") or "(unknown file)"
                            fid = c.get("file_id") or "(no id)"
                            st.write(f"- {fn} [{fid}]")
                else:
                    st.info("No output returned.")
            except Exception as e:
                st.error(f"An error occurred: {e}")

st.divider()
# Sidebar: Settings + Knowledge Base
kb = st.sidebar

# Settings section: set OpenAI API key and model directly from dashboard
kb.header("Settings")
kb.caption("Provide your OpenAI API key and preferred model.")
kb.text_input("OpenAI API Key", type="password", key="OPENAI_API_KEY")
if st.session_state.get("OPENAI_API_KEY"):
    kb.success("API key set")
else:
    kb.warning("Set your API key to enable OpenAI features.")
kb.text_input("Model", key="OPENAI_MODEL")

kb.header("Knowledge Base")
kb.caption("Upload files, select/create vector stores, and manage existing files.")

# Active vector store controls (sidebar)


vs_name = kb.text_input("New Vector Store Name", value="knowledge_base")
if kb.button("Create New Vector Store", key="btn_create_vs"):
    try:
        if not st.session_state.get("OPENAI_API_KEY"):
            kb.error("Set your OpenAI API key in Settings first.")
        else:
            created_vs = client.vector_stores.create(name=vs_name)
            st.session_state["ACTIVE_VECTOR_STORE_ID"] = created_vs.id
            kb.success(f"Created new vector store: {created_vs.id}")
    except Exception as e:
        kb.error(f"Failed to create vector store: {e}")

# Vector stores overview and actions (sidebar)
kb.subheader("Vector Stores")
# Small refresh button close to header
if kb.button("↻ Refresh", key="btn_refresh_stores"):
    st.rerun()

def list_vector_stores():
    try:
        if not st.session_state.get("OPENAI_API_KEY") or not client:
            kb.info("Set your OpenAI API key in Settings to load stores.")
            return []
        listing = client.vector_stores.list()
        return getattr(listing, "data", [])
    except Exception as e:
        # Occasionally right after a deletion, the SDK may return a transient 404 while the backend refreshes
        if "Vector store not found" in str(e):
            kb.info("Refreshing stores...")
            st.rerun()
        else:
            kb.error(f"Failed to list vector stores: {e}")
        return []

active_id = get_active_vector_store_id()
stores = list_vector_stores()
for vs in stores:
    vs_id = getattr(vs, "id", "")
    vs_name = getattr(vs, "name", "(unnamed)")
    label = f"{vs_name} ({vs_id})"
    with kb.expander(label, expanded=(vs_id == active_id)):
        # Active badge and set active action
        if vs_id == active_id:
            kb.success("Active")
        else:
            if kb.button("Set Active", key=f"btn_set_active_{vs_id}"):
                st.session_state["ACTIVE_VECTOR_STORE_ID"] = vs_id
                kb.success(f"Active vector store set: {vs_id}")

        # Delete vector store action (also delete related files)
        if kb.button("Delete Store", key=f"btn_delete_store_{vs_id}"):
            try:
                if not client:
                    kb.error("Set your OpenAI API key in Settings first.")
                else:
                    # 1) List files associated with this store
                    try:
                        listing = client.vector_stores.files.list(vector_store_id=vs_id)
                        refs = getattr(listing, "data", [])
                    except Exception:
                        refs = []
                    deleted_files = 0
                    for ref in refs:
                        fid = getattr(ref, "file_id", None) or getattr(ref, "id", None)
                        if not fid:
                            continue
                        # 2) Detach from vector store (best-effort)
                        try:
                            client.vector_stores.files.delete(vector_store_id=vs_id, file_id=fid)
                        except Exception:
                            pass
                        # 3) Delete file from Files API
                        try:
                            client.files.delete(fid)
                            deleted_files += 1
                        except Exception as e:
                            kb.warning(f"Failed to delete file {fid}: {e}")

                    # 4) Delete the vector store
                    client.vector_stores.delete(vector_store_id=vs_id)
                    # Clear active if we just deleted it
                    if get_active_vector_store_id() == vs_id:
                        st.session_state["ACTIVE_VECTOR_STORE_ID"] = None
                    kb.success(f"Deleted vector store: {vs_id} (and {deleted_files} related files)")
                    st.rerun()
            except Exception as e:
                kb.error(f"Failed to delete vector store {vs_id}: {e}")

        # Show files toggle for any selected store
        show_files = kb.checkbox("Show files", key=f"chk_show_files_{vs_id}")
        if show_files:
            try:
                if not client:
                    kb.info("Set your OpenAI API key in Settings to load files.")
                else:
                    listing = client.vector_stores.files.list(vector_store_id=vs_id)
                    refs = getattr(listing, "data", [])
                    if not refs:
                        kb.write("No files.")
                    else:
                        for ref in refs:
                            fid = getattr(ref, "file_id", None) or getattr(ref, "id", None)
                            filename = None
                            if fid:
                                try:
                                    fobj = client.files.retrieve(fid)
                                    filename = getattr(fobj, "filename", None) or getattr(fobj, "name", None)
                                except Exception:
                                    filename = None
                            # Compact row in sidebar: filename left, delete button right
                            col1, col2 = kb.columns([6, 2])
                            with col1:
                                kb.write(filename or "(unknown)")
                            with col2:
                                if kb.button("Delete", key=f"btn_del_{vs_id}_{fid}"):
                                    try:
                                        client.vector_stores.files.delete(vector_store_id=vs_id, file_id=fid)
                                        kb.success(f"Deleted: {filename or fid}")
                                        st.rerun()
                                    except Exception as e:
                                        kb.error(f"Failed to delete {filename or fid}: {e}")
            except Exception as e:
                # Suppress transient 404s for recently deleted stores
                if "Vector store not found" in str(e):
                    kb.info("Store was deleted. Refreshing...")
                    st.rerun()
                else:
                    kb.error(f"Failed to list files for store: {e}")


# Poll until a file is indexed in the active vector store

def wait_until_file_indexed(file_id: str, timeout_sec: int = 60, poll_interval: float = 1.0):
    start = time.time()
    while time.time() - start < timeout_sec:
        try:
            listing = client.vector_stores.files.list(vector_store_id=get_active_vector_store_id())
            data = getattr(listing, "data", [])
            for f in data:
                if getattr(f, "id", "") == file_id:
                    status = getattr(f, "status", "")
                    if status in ("completed", "finished"):
                        return "completed"
                    if status in ("failed", "error"):
                        return status
            time.sleep(poll_interval)
        except Exception:
            time.sleep(poll_interval)
    return "timeout"

# Upload section
uploaded_files = kb.file_uploader(
    "Upload files to active vector store",
    type=["pdf", "txt", "md", "json", "docx", "pptx", "html", "py", "java", "js", "ts"],
    accept_multiple_files=True,
    help="Supported types are aligned with OpenAI File Search accepted formats."
)

if kb.button("Upload"):
    if not uploaded_files:
        kb.warning("Please choose one or more files to upload.")
    elif not get_active_vector_store_id():
        kb.error("No active vector store set. Create one or set an ID above.")
    elif not client:
        kb.error("Set your OpenAI API key in Settings first.")
    else:
        with st.spinner("Uploading and indexing files..."):
            results = []
            for uf in uploaded_files:
                try:
                    # 1) Upload the file to the File API
                    content = uf.getvalue()
                    file_tuple = (uf.name, io.BytesIO(content))
                    created = client.files.create(file=file_tuple, purpose="assistants")

                    # 2) Add the file to the active vector store
                    client.vector_stores.files.create(
                        vector_store_id=get_active_vector_store_id(),
                        file_id=created.id,
                    )

                    # 3) Check status by polling
                    status = wait_until_file_indexed(created.id, timeout_sec=90)
                    results.append((uf.name, created.id, status))
                except Exception as e:
                    kb.error(f"Failed to upload {uf.name}: {e}")
            kb.success("Upload finished:")
            for name, fid, status in results:
                kb.write(f"- {name} [{fid}] status: {status}")


# Optional helper to show which vector store is configured