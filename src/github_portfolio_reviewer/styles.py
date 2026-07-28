"""GitHub-inspired visual system for the Streamlit presentation layer."""

THEME_TOKENS = {
    "Dark": {
        "color-scheme": "dark",
        "canvas": "#0d1117",
        "surface": "#161b22",
        "surface-raised": "#1c2128",
        "border": "#30363d",
        "border-muted": "#21262d",
        "text": "#e6edf3",
        "muted": "#8b949e",
        "subtle": "#6e7681",
        "blue": "#58a6ff",
        "green": "#3fb950",
        "green-button": "#238636",
        "green-button-hover": "#1f7a32",
        "amber": "#d29922",
        "red": "#f85149",
        "shadow": "rgba(1, 4, 9, 0.45)",
    },
    "Light": {
        "color-scheme": "light",
        "canvas": "#ffffff",
        "surface": "#f6f8fa",
        "surface-raised": "#ffffff",
        "border": "#d0d7de",
        "border-muted": "#d8dee4",
        "text": "#1f2328",
        "muted": "#59636e",
        "subtle": "#6e7781",
        "blue": "#0969da",
        "green": "#1a7f37",
        "green-button": "#1f883d",
        "green-button-hover": "#1a7f37",
        "amber": "#9a6700",
        "red": "#cf222e",
        "shadow": "rgba(31, 35, 40, 0.12)",
    },
}


def github_native_css(theme: str) -> str:
    """Return the visual system with dark or light GitHub-style tokens."""
    tokens = THEME_TOKENS.get(theme, THEME_TOKENS["Dark"])
    variables = "\n".join(f"    --{name}: {value};" for name, value in tokens.items())
    return f"<style>\n:root {{\n{variables}\n}}\n{COMPONENT_CSS}\n</style>"


COMPONENT_CSS = """
* {
    box-sizing: border-box;
}

html {
    color-scheme: var(--color-scheme);
}

.stApp {
    background: var(--canvas);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}

.block-container {
    max-width: 1180px;
    padding-bottom: 4rem;
    padding-top: 1.5rem;
}

[data-testid="stHeader"],
[data-testid="stSidebar"],
[data-testid="stToolbar"],
[data-testid="stAppDeployButton"],
#MainMenu,
footer {
    display: none !important;
}

h1 {
    color: var(--text) !important;
    font-size: 2rem !important;
    font-weight: 600 !important;
    letter-spacing: -0.025em !important;
    margin: 0.2rem 0 0.1rem !important;
}

h2.section-heading,
.section-heading {
    color: var(--muted);
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    margin: 1.35rem 0 0.75rem;
}

h3,
h4 {
    color: var(--text) !important;
}

p,
label,
[data-testid="stCaptionContainer"] {
    color: var(--muted);
}

[data-testid="stCaptionContainer"] {
    font-size: 0.8rem;
}

.product-brand {
    align-items: center;
    color: var(--text);
    display: flex;
    gap: 0.7rem;
}

.product-mark {
    align-items: center;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 6px;
    color: var(--blue);
    display: inline-flex;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 0.75rem;
    height: 2rem;
    justify-content: center;
    width: 2rem;
}

.product-brand strong {
    display: block;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 0.9rem;
    font-weight: 600;
}

.product-brand small {
    color: var(--muted);
    display: block;
    font-size: 0.72rem;
    margin-top: 0.08rem;
}

.product-divider {
    border-top: 1px solid var(--border-muted);
    margin: 0.75rem 0 1.55rem;
}

.app-kicker,
.score-label,
.repo-fact dt,
.recommendation-details span,
.target-file span {
    color: var(--muted);
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 0.7rem;
    font-weight: 600;
    letter-spacing: 0.08em;
}

.api-mode {
    align-items: center;
    color: var(--muted);
    display: flex;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 0.7rem;
    gap: 0.45rem;
    justify-content: flex-end;
    white-space: nowrap;
}

.api-mode span {
    background: var(--green);
    border-radius: 50%;
    box-shadow: 0 0 0 3px color-mix(in srgb, var(--green) 14%, transparent);
    height: 0.45rem;
    width: 0.45rem;
}

[data-testid="stPopoverBody"] {
    background: var(--surface-raised) !important;
    border: 1px solid var(--border) !important;
    box-shadow: 0 8px 24px var(--shadow) !important;
    color: var(--text) !important;
}

[data-testid="stPopover"] button,
.stButton button,
.stLinkButton a {
    background: var(--surface) !important;
    border: 1px solid var(--border) !important;
    border-radius: 6px !important;
    color: var(--text) !important;
    font-size: 0.8rem !important;
    font-weight: 500 !important;
}

[data-testid="stPopover"] button:hover,
.stButton button:hover,
.stLinkButton a:hover {
    background: var(--surface-raised) !important;
    border-color: var(--subtle) !important;
}

button:focus-visible,
a:focus-visible,
input:focus-visible,
[role="tab"]:focus-visible,
[role="radio"]:focus-visible {
    outline: 2px solid var(--blue) !important;
    outline-offset: 2px !important;
}

div[data-testid="stForm"] {
    background: var(--surface);
    border: 1px solid var(--border) !important;
    border-radius: 6px !important;
    margin-top: 1.35rem;
    padding: 1rem 1rem 0.7rem;
}

.form-heading {
    color: var(--text);
    font-size: 0.88rem;
    font-weight: 600;
    margin-bottom: 0.25rem;
}

[data-baseweb="input"],
[data-baseweb="select"] > div,
[data-testid="stTextInputRootElement"] {
    background: var(--canvas) !important;
    border-color: var(--border) !important;
    border-radius: 6px !important;
    color: var(--text) !important;
}

[data-baseweb="input"] input {
    color: var(--text) !important;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}

[data-testid="stTextInputRootElement"] input {
    color: var(--text) !important;
}

[data-baseweb="input"] input::placeholder {
    color: var(--subtle) !important;
    opacity: 1;
}

[data-baseweb="popover"],
[role="listbox"] {
    background: var(--surface-raised) !important;
    color: var(--text) !important;
}

.stButton button[kind="primary"],
[data-testid="stFormSubmitButton"] button {
    background: var(--green-button) !important;
    border: 1px solid rgba(255, 255, 255, 0.12) !important;
    color: #ffffff !important;
    font-weight: 600 !important;
}

.stButton button[kind="primary"]:hover,
[data-testid="stFormSubmitButton"] button:hover {
    background: var(--green-button-hover) !important;
}

.scope-line {
    align-items: center;
    color: var(--muted);
    display: flex;
    flex-wrap: wrap;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 0.7rem;
    gap: 0.55rem 1.2rem;
    margin-top: 0.25rem;
}

.scope-line span::before {
    color: var(--green);
    content: "✓";
    margin-right: 0.35rem;
}

.empty-workspace {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 6px;
    display: grid;
    gap: 2rem;
    grid-template-columns: 1.65fr 1fr;
    margin-top: 1.4rem;
    padding: 1.5rem;
}

.empty-workspace .section-heading {
    margin-top: 0;
}

.empty-copy h3 {
    font-size: 1rem;
    margin: 0 0 0.45rem;
}

.empty-copy p {
    font-size: 0.82rem;
    line-height: 1.55;
    margin: 0;
    max-width: 680px;
}

.scope-pills {
    display: flex;
    flex-wrap: wrap;
    gap: 0.45rem;
    margin-top: 1rem;
}

.scope-pills span {
    background: var(--canvas);
    border: 1px solid var(--border);
    border-radius: 999px;
    color: var(--muted);
    font-size: 0.72rem;
    padding: 0.2rem 0.55rem;
}

.workflow-list {
    border-left: 1px solid var(--border);
    display: grid;
    gap: 0.9rem;
    padding-left: 1.4rem;
}

.workflow-list div {
    display: grid;
    gap: 0.08rem 0.65rem;
    grid-template-columns: 28px 1fr;
}

.workflow-list span {
    color: var(--blue);
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 0.72rem;
    grid-row: 1 / 3;
    padding-top: 0.12rem;
}

.workflow-list strong {
    color: var(--text);
    font-size: 0.8rem;
}

.workflow-list small {
    color: var(--muted);
    font-size: 0.72rem;
}

[data-testid="stStatusWidget"],
[data-testid="stAlertContainer"] {
    background: var(--surface) !important;
    border-color: var(--border) !important;
    color: var(--text) !important;
}

.report-divider {
    border-top: 1px solid var(--border);
    margin: 2rem 0 1.5rem;
}

.repository-heading {
    align-items: center;
    display: flex;
    flex-wrap: wrap;
    gap: 0.8rem;
}

.repo-path {
    color: var(--blue) !important;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 1.18rem;
    font-weight: 600;
    text-decoration: none;
}

.repo-path:hover {
    text-decoration: underline;
}

.repo-labels {
    display: inline-flex;
    gap: 0.35rem;
}

.repo-label {
    border: 1px solid color-mix(in srgb, var(--blue) 45%, transparent);
    border-radius: 999px;
    color: var(--blue);
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 0.65rem;
    font-weight: 600;
    padding: 0.12rem 0.42rem;
}

.repo-label-muted {
    border-color: var(--border);
    color: var(--muted);
}

.repo-description {
    color: var(--muted);
    font-size: 0.88rem;
    margin: 0.65rem 0 1.1rem;
}

.summary-grid {
    display: grid;
    gap: 0;
    grid-template-columns: minmax(210px, 1.55fr) repeat(4, minmax(105px, 1fr));
    margin-top: 0.55rem;
}

.score-card,
.signal-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-right: 0;
    min-width: 0;
    padding: 1rem;
}

.score-card {
    border-radius: 6px 0 0 6px;
}

.signal-card:last-child {
    border-radius: 0 6px 6px 0;
    border-right: 1px solid var(--border);
}

.score-value {
    color: var(--text);
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 2.2rem;
    font-weight: 600;
    line-height: 1.12;
    margin: 0.2rem 0 0.05rem;
}

.score-value span {
    color: var(--muted);
    font-size: 0.85rem;
    font-weight: 400;
}

.score-band {
    color: var(--muted);
    font-size: 0.75rem;
}

.score-track {
    background: var(--border-muted);
    border-radius: 2px;
    height: 4px;
    margin-top: 0.75rem;
    overflow: hidden;
}

.score-track span {
    background: var(--green);
    display: block;
    height: 100%;
}

.signal-card {
    display: flex;
    flex-direction: column;
    justify-content: center;
}

.signal-card > span {
    color: var(--muted);
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 0.67rem;
    font-weight: 600;
    letter-spacing: 0.06em;
}

.signal-card strong {
    color: var(--text);
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 1.25rem;
    margin: 0.2rem 0 0.05rem;
}

.signal-card small {
    color: var(--muted);
    font-size: 0.68rem;
}

.signal-pass strong {
    color: var(--green);
}

.signal-partial strong {
    color: var(--amber);
}

.signal-fail strong {
    color: var(--red);
}

.signal-opportunity strong {
    color: var(--blue);
}

.repo-facts {
    background: var(--canvas);
    border-bottom: 1px solid var(--border-muted);
    display: grid;
    gap: 0.9rem 1.4rem;
    grid-template-columns: repeat(6, minmax(0, 1fr));
    margin: 0;
    padding: 1rem 0;
}

.repo-fact {
    display: flex;
    flex-direction: column;
    gap: 0.18rem;
    min-width: 0;
}

.repo-fact dd {
    color: var(--text);
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 0.78rem;
    font-weight: 500;
    margin: 0;
    overflow-wrap: anywhere;
}

.stTabs [data-baseweb="tab-list"] {
    border-bottom: 1px solid var(--border);
    gap: 1.25rem;
    margin-top: 0.65rem;
}

.stTabs [data-baseweb="tab"] {
    background: transparent !important;
    color: var(--muted) !important;
    font-size: 0.8rem;
    padding: 0.65rem 0.1rem;
}

.stTabs [aria-selected="true"] {
    color: var(--text) !important;
}

.stTabs [data-baseweb="tab-highlight"] {
    background-color: var(--green) !important;
}

.projection-line {
    color: var(--muted);
    font-size: 0.75rem;
    margin: -0.25rem 0 0.65rem;
}

.projection-line strong {
    color: var(--blue);
}

.category-list,
.check-list {
    border: 1px solid var(--border);
    border-radius: 6px;
    overflow: hidden;
}

.category-row {
    align-items: center;
    background: var(--surface);
    border-bottom: 1px solid var(--border-muted);
    display: grid;
    gap: 1rem;
    grid-template-columns: minmax(120px, 1.45fr) minmax(90px, 2fr) 66px;
    padding: 0.72rem 0.8rem;
}

.category-row:last-child {
    border-bottom: 0;
}

.category-name {
    color: var(--text);
    font-size: 0.78rem;
}

.category-track {
    background: var(--border-muted);
    border-radius: 2px;
    height: 4px;
    overflow: hidden;
}

.category-track span {
    background: var(--green);
    display: block;
    height: 100%;
}

.category-points,
.check-points,
.potential-points,
.recommendation-index {
    color: var(--muted);
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 0.72rem;
    text-align: right;
}

.method-note,
.filter-result {
    color: var(--muted);
    font-size: 0.72rem;
    margin-top: 0.7rem;
}

.filter-result {
    margin: 0.8rem 0;
}

.check-group-heading {
    align-items: center;
    display: flex;
    justify-content: space-between;
    margin: 1rem 0 0.4rem;
}

.check-group-heading span {
    color: var(--text);
    font-size: 0.78rem;
    font-weight: 600;
}

.check-group-heading small {
    color: var(--muted);
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 0.7rem;
}

.check-row {
    background: var(--surface);
    border-bottom: 1px solid var(--border-muted);
    padding: 0.78rem;
}

.check-row:last-child {
    border-bottom: 0;
}

.check-header {
    align-items: center;
    display: grid;
    gap: 0.65rem;
    grid-template-columns: 64px 1fr 48px;
}

.status,
.priority {
    border: 1px solid;
    border-radius: 999px;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 0.62rem;
    font-weight: 700;
    letter-spacing: 0.04em;
    padding: 0.1rem 0.35rem;
    text-align: center;
}

.status-pass {
    background: color-mix(in srgb, var(--green) 11%, transparent);
    border-color: color-mix(in srgb, var(--green) 45%, transparent);
    color: var(--green);
}

.status-partial,
.priority-medium {
    background: color-mix(in srgb, var(--amber) 10%, transparent);
    border-color: color-mix(in srgb, var(--amber) 45%, transparent);
    color: var(--amber);
}

.status-fail,
.priority-high {
    background: color-mix(in srgb, var(--red) 9%, transparent);
    border-color: color-mix(in srgb, var(--red) 45%, transparent);
    color: var(--red);
}

.priority-low {
    background: color-mix(in srgb, var(--blue) 9%, transparent);
    border-color: color-mix(in srgb, var(--blue) 45%, transparent);
    color: var(--blue);
}

.check-title {
    color: var(--text);
    font-size: 0.8rem;
    font-weight: 500;
}

.check-evidence {
    color: var(--muted);
    font-size: 0.75rem;
    line-height: 1.45;
    margin: 0.35rem 0 0 4.95rem;
}

.recommendation-row {
    align-items: flex-start;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 6px;
    display: grid;
    gap: 0.8rem;
    grid-template-columns: 32px 1fr 58px;
    margin-bottom: 0.5rem;
    padding: 0.85rem;
}

.recommendation-index {
    padding-top: 0.15rem;
    text-align: left;
}

.recommendation-header {
    align-items: center;
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
}

.recommendation-header strong {
    color: var(--text);
    font-size: 0.8rem;
    font-weight: 600;
}

.recommendation-category {
    color: var(--muted);
    font-size: 0.7rem;
}

.recommendation-action {
    color: var(--muted);
    font-size: 0.75rem;
    line-height: 1.45;
    margin: 0.35rem 0 0;
}

.target-file {
    align-items: center;
    display: flex;
    gap: 0.5rem;
    margin-top: 0.5rem;
}

.target-file code {
    background: var(--canvas);
    border: 1px solid var(--border-muted);
    border-radius: 4px;
    color: var(--text);
    font-size: 0.7rem;
    padding: 0.1rem 0.35rem;
}

.recommendation-details {
    border-top: 1px solid var(--border-muted);
    display: grid;
    gap: 0.8rem;
    grid-template-columns: 1fr 1fr;
    margin-top: 0.7rem;
    padding-top: 0.7rem;
}

.recommendation-details p {
    color: var(--muted);
    font-size: 0.72rem;
    line-height: 1.4;
    margin: 0.2rem 0 0;
}

.potential-points {
    padding-top: 0.15rem;
    white-space: nowrap;
}

[data-testid="stExpander"] {
    background: var(--surface);
    border: 1px solid var(--border) !important;
    border-radius: 6px !important;
}

.empty-state {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 6px;
    color: var(--muted);
    font-size: 0.8rem;
    padding: 1rem;
}

hr {
    border-color: var(--border) !important;
}

@media (max-width: 900px) {
    .summary-grid {
        grid-template-columns: repeat(4, minmax(90px, 1fr));
    }

    .score-card {
        border-radius: 6px 6px 0 0;
        border-right: 1px solid var(--border);
        grid-column: 1 / -1;
    }

    .signal-card {
        border-top: 0;
    }

    .signal-card:nth-child(2) {
        border-radius: 0 0 0 6px;
    }

    .repo-facts {
        grid-template-columns: repeat(3, minmax(0, 1fr));
    }
}

@media (max-width: 760px) {
    .block-container {
        padding: 1rem 0.85rem 3rem;
    }

    .product-brand small,
    .api-mode {
        display: none;
    }

    h1 {
        font-size: 1.7rem !important;
    }

    .empty-workspace {
        grid-template-columns: 1fr;
    }

    .workflow-list {
        border-left: 0;
        border-top: 1px solid var(--border);
        padding-left: 0;
        padding-top: 1rem;
    }

    .repo-facts {
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .category-row {
        gap: 0.7rem;
        grid-template-columns: 1fr 58px;
    }

    .category-track {
        display: none;
    }

    .check-evidence {
        margin-left: 0;
    }

    .recommendation-row {
        grid-template-columns: 28px 1fr;
    }

    .potential-points {
        grid-column: 2;
        padding-top: 0;
        text-align: left;
    }

    .recommendation-details {
        grid-template-columns: 1fr;
    }

    .stTabs [data-baseweb="tab-list"] {
        gap: 0.8rem;
        overflow-x: auto;
    }
}

@media (max-width: 520px) {
    .summary-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .score-card {
        grid-column: 1 / -1;
    }

    .signal-card:nth-child(2) {
        border-radius: 0;
    }

    .signal-card:nth-child(3) {
        border-right: 1px solid var(--border);
    }

    .signal-card:nth-child(4) {
        border-radius: 0 0 0 6px;
    }

    .signal-card:last-child {
        border-radius: 0 0 6px 0;
    }
}
"""
