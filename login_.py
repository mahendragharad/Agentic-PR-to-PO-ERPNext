import hashlib
import time

import httpx
import streamlit as st

import streamlit as st

# Automatically checks Streamlit Secrets in the cloud, falls back to local host for offline testing
BASE_API_URL = st.secrets.get("BACKEND_API_URL", "http://127.0.0.1:8001")

# Dynamically builds the final production routing path
LOGIN_URL = f"{BASE_API_URL}/api/v2/user/auth/login"


# LOGIN_URL = "http://127.0.0.1:8001/api/v2/user/auth/login"
AUTH_COOKIE_NAME = "erpnext_auth_token"


def _user_id_for(username: str) -> str:
    normalized_username = username.strip().casefold()
    prefix = "".join(
        char if char.isalnum() else "-"
        for char in normalized_username[:3]
    ).strip("-") or "usr"
    username_hash = hashlib.sha256(normalized_username.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_dummy_{username_hash}"


def clear_authentication() -> None:
    st.session_state.erpnext_auth_cookie = None
    st.session_state.user_id = None


def render_login_page() -> None:
    # 1. Global Page & Layout Styling
    st.markdown(
        """
        <style>
        /* Hide the default Streamlit sidebar completely */
        [data-testid="stSidebar"] { display: none !important; }
        
        /* Hide default headers and padding for a clean canvas */
        header[data-testid="stHeader"] { display: none !important; }
        .block-container {
            padding-top: 0rem !important;
            padding-bottom: 0rem !important;
            max-width: 100% !important;
            height: 100vh;
            display: flex;
            align-items: center;
        }

        /* Light elegant background */
        .stApp {
            background: linear-gradient(135deg, #F8FAFC 0%, #E2E8F0 50%, #DBEAFE 100%);
        }

        /* Fix the column layout heights to center content vertically */
        div[data-testid="column"] {
            display: flex;
            flex-direction: column;
            justify-content: center;
        }

        /* ---------- LEFT COLUMN: Branding ---------- */
        .brand-badge {
            display: inline-flex;
            align-items: center;
            gap: .5rem;
            padding: .45rem 1rem;
            border-radius: 999px;
            background: #FFFFFF;
            border: 1px solid #CBD5E1;
            color: #1E293B;
            font-size: .8rem;
            font-weight: 700;
            letter-spacing: .08em;
            text-transform: uppercase;
            width: fit-content;
            margin-bottom: 1.5rem;
            box-shadow: 0 4px 10px rgba(0,0,0,0.03);
        }
        .brand-badge .dot {
            width: 8px; height: 8px; border-radius: 50%;
            background: #22D3EE;
            box-shadow: 0 0 10px #22D3EE;
        }

        .brand-title {
            font-size: 3.8rem;
            line-height: 1.05;
            font-weight: 800;
            color: #0F172A; /* Dark Blue/Black */
            margin: 0 0 1.2rem 0;
            letter-spacing: -.02em;
        }
        .brand-title .accent {
            background: linear-gradient(90deg, #06B6D4 0%, #8B5CF6 50%, #EC4899 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }

        .brand-subtitle {
            font-size: 1.1rem;
            line-height: 1.6;
            color: #334155; /* Dark Slate */
            margin: 0 0 2.5rem 0;
        }

        .feature-item {
            display: flex;
            align-items: center;
            gap: .9rem;
            color: #1E293B;
            font-size: .95rem;
            font-weight: 500;
            margin-bottom: 1rem;
        }
        .feature-item .tick {
            flex-shrink: 0;
            width: 28px; height: 28px;
            border-radius: 8px;
            display: flex; align-items: center; justify-content: center;
            background: linear-gradient(135deg, #06B6D4, #8B5CF6);
            color: #fff;
            font-size: .85rem;
            font-weight: 700;
            box-shadow: 0 4px 12px rgba(139,92,246,.3);
        }

        /* ---------- CENTER DIVIDER ---------- */
        /* We use a pseudo-element on the right column to create the vertical line */
        div[data-testid="column"]:nth-of-type(2)::before {
            content: "";
            position: absolute;
            left: -2.5rem; /* Adjust distance from card */
            top: 10%;
            height: 80%;
            width: 1px;
            background: linear-gradient(to bottom, transparent, #CBD5E1, transparent);
        }

        /* ---------- RIGHT COLUMN: Login Card ---------- */
        [data-testid="stForm"] {
            background: #FFFFFF !important;
            border-radius: 20px !important;
            padding: 2.5rem 2rem !important;
            box-shadow: 0 20px 50px rgba(15, 23, 42, 0.1), 0 0 0 1px rgba(0,0,0,0.05) !important;
            border: none !important;
            position: relative;
        }

        /* Gradient border effect for the card */
        [data-testid="stForm"]::before {
            content: "";
            position: absolute;
            inset: -2px;
            border-radius: 22px;
            padding: 2px;
            background: linear-gradient(135deg, #22D3EE, #8B5CF6, #F472B6);
            -webkit-mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
            -webkit-mask-composite: xor;
            mask-composite: exclude;
            pointer-events: none;
        }

        /* Form internal text */
        .login-header {
            font-size: 1.8rem;
            font-weight: 800;
            color: #0F172A;
            margin-bottom: 0.2rem;
            margin-top: -0.5rem;
        }
        .login-sub {
            color: #64748B;
            font-size: 0.95rem;
            margin-bottom: 1.5rem;
        }

        /* Input Fields */
        [data-testid="stForm"] label {
            font-size: .85rem !important;
            font-weight: 600 !important;
            color: #334155 !important;
        }
        [data-testid="stForm"] input {
            background: #F8FAFC !important;
            border: 1.5px solid #E2E8F0 !important;
            border-radius: 10px !important;
            padding: .75rem 1rem !important;
            color: #0F172A !important;
            transition: all 0.2s ease !important;
        }
        [data-testid="stForm"] input:focus {
            border-color: #8B5CF6 !important;
            background: #FFFFFF !important;
            box-shadow: 0 0 0 4px rgba(139,92,246,.15) !important;
        }

        /* Submit Button */
        [data-testid="stFormSubmitButton"] button {
            width: 100%;
            border: none !important;
            border-radius: 10px !important;
            padding: .8rem 1rem !important;
            font-size: 1rem !important;
            font-weight: 700 !important;
            color: #FFFFFF !important;
            background: linear-gradient(90deg, #06B6D4 0%, #8B5CF6 55%, #EC4899 100%) !important;
            background-size: 200% auto !important;
            box-shadow: 0 10px 25px rgba(139,92,246,.3) !important;
            transition: all 0.3s ease !important;
            margin-top: 0.5rem;
        }
        [data-testid="stFormSubmitButton"] button:hover {
            background-position: right center !important;
            transform: translateY(-1px);
            box-shadow: 0 12px 30px rgba(236,72,153,.4) !important;
        }

        .login-foot {
            margin-top: 1.5rem;
            text-align: center;
            font-size: .8rem;
            color: #94A3B8;
        }

        /* Alerts (Error/Success) */
        .login-card [data-testid="stAlert"] {
            border-radius: 10px;
            font-size: 0.85rem;
            padding: 0.5rem 1rem;
            margin-bottom: 1rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # 2. Create the layout (Spacing handled by ratio)
    # Empty space on edges to center the main content
    _, main_col1, main_col2, _ = st.columns([0.5, 2, 1.5, 0.5], gap="large")

    # 3. Render Left Column (Branding)
    with main_col1:
        st.markdown(
            """
            <div>
                <div class="brand-badge"><span class="dot"></span> Intelligent Procurement</div>
                <h1 class="brand-title">
                    Intelligent<br/>
                    <span class="accent">Procurement Hub</span>
                </h1>
                <p class="brand-subtitle">
                    Streamline sourcing, purchasing, and supplier collaboration in one
                    beautifully unified workspace — powered by your ERPNext data.
                </p>
                <div class="feature-item"><span class="tick">✓</span> Real-time purchase order tracking</div>
                <div class="feature-item"><span class="tick">✓</span> Smart supplier &amp; vendor insights</div>
                <div class="feature-item"><span class="tick">✓</span> Secure, single sign-on with ERPNext</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # 4. Render Right Column (Login Card)
    with main_col2:
        with st.form("erpnext_login"):
            st.markdown(
                '<div class="login-header">Welcome back</div>'
                '<div class="login-sub">Sign in with your ERPNext account to continue.</div>',
                unsafe_allow_html=True,
            )
            
            username = st.text_input("ERPNext username", placeholder="you@company.com")
            password = st.text_input("ERPNext password", type="password", placeholder="••••••••")
            
            # Placeholder for error/success messages inside the card
            alert_placeholder = st.empty()
            
            login_submitted = st.form_submit_button("Log in", use_container_width=True)
            
            st.markdown(
                '<div class="login-foot">Protected access · ERPNext authentication</div>',
                unsafe_allow_html=True,
            )

    # 5. Handle Login Logic
    if login_submitted:
        if not username.strip() or not password:
            alert_placeholder.error("Please enter both your ERPNext username and password.")
            return

        try:
            response = httpx.post(
                LOGIN_URL,
                data={"username": username, "password": password},
                timeout=20.0,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            # Show failure message clearly
            alert_placeholder.error("Login failed. Please check your credentials and try again.")
            return

        auth_cookie = response.cookies.get(AUTH_COOKIE_NAME)
        if not auth_cookie:
            alert_placeholder.error("Login failed. No authentication token received.")
            return

        # Show success message
        alert_placeholder.success("Login successful! Redirecting...")
        
        # Save state
        st.session_state.erpnext_auth_cookie = auth_cookie
        st.session_state.user_id = _user_id_for(username)
        
        # Brief pause so the user can see the success message
        time.sleep(1.2)
        st.rerun()