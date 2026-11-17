import streamlit as st
import pandas as pd
import numpy as np
from scipy import stats
from scipy.special import gammaln
import plotly.graph_objects as go
import re
from io import BytesIO
import zipfile

st.set_page_config(page_title="Minitab DIY", layout="wide")
st.title("Minitab DIY")

# --- Functions ---
def hex_to_rgba(hex_color, opacity=0.85):
    hex_color = hex_color.lstrip('#')
    r, g, b = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    return f"rgba({r}, {g}, {b}, {opacity})"

def parse_spec_from_col(col_name):
    match = re.search(r"(\d+\.\d+)\s*[±\+\-]\s*(\d+\.\d+)", str(col_name))
    if match:
        target = float(match.group(1))
        tol = float(match.group(2))
        return round(target - tol, 6), target, round(target + tol, 6)
    return 0.3265, 0.3280, 0.3295

def fmt6(v):
    return np.format_float_positional(float(v), precision=6, unique=False, fractional=False, trim='-')

def c4(n):
    return np.sqrt(2.0 / (n - 1)) * np.exp(gammaln(n / 2.0) - gammaln((n - 1) / 2.0))

def calc_within(values, subgroup_size=1):
    x = np.asarray(values, dtype=float)
    if subgroup_size <= 1:
        mr = np.abs(np.diff(x))
        return mr.mean() / 1.128 if len(mr) > 0 else np.nan
    groups = [x[i:i + subgroup_size] for i in range(0, len(x), subgroup_size)]
    groups = [g for g in groups if len(g) > 1]
    if not groups:
        return np.nan
    ss = sum(((g - g.mean()) ** 2).sum() for g in groups)
    d = sum(len(g) - 1 for g in groups)
    return np.sqrt(ss / d) / c4(d + 1)

# --- Init Data ---
if "df" not in st.session_state:
    np.random.seed(42)
    df_init = pd.DataFrame({
        "B1_0.328 ± 0.0015": np.round(np.random.normal(0.3283, 0.00012, 32), 4),
        "B2_0.2845 ± 0.0015": np.round(np.random.normal(0.2843, 0.00012, 32), 4),
        "B3_0.2443 ± 0.0015": np.round(np.random.normal(0.2446, 0.00010, 32), 4),
        "B4_0.2008 ± 0.0015": np.round(np.random.normal(0.2010, 0.00011, 32), 4),
        "Cavity": [1]*16 + [2]*16
    })
    df_init.index = np.arange(1, len(df_init) + 1)
    df_init.index.name = "Row"
    st.session_state.df = df_init

if "editor_ver" not in st.session_state:
    st.session_state.editor_ver = 0

# --- Sidebar: 1. ข้อมูล ---
st.sidebar.header("📁 ข้อมูล (Data)")
uploaded_file = st.sidebar.file_uploader("อัปโหลดไฟล์", type=["xlsx", "csv"], label_visibility="collapsed")

col_btn1, col_btn2 = st.sidebar.columns(2)
with col_btn1:
    if st.button("📥 โหลดไฟล์", use_container_width=True) and uploaded_file:
        if uploaded_file.name.endswith(".csv"):
            temp_df = pd.read_csv(uploaded_file)
        else:
            temp_df = pd.read_excel(uploaded_file)
        temp_df.index = np.arange(1, len(temp_df) + 1)
        temp_df.index.name = "Row"
        st.session_state.df = temp_df
        st.session_state.editor_ver += 1
with col_btn2:
    if st.button("🧹 ล้างค่า", use_container_width=True):
        empty_df = pd.DataFrame({"B1_0.328 ± 0.0015": [np.nan]*10, "Cavity": [1]*10})
        empty_df.index = np.arange(1, len(empty_df) + 1)
        empty_df.index.name = "Row"
        st.session_state.df = empty_df
        st.session_state.editor_ver += 1

st.session_state.df.index = np.arange(1, len(st.session_state.df) + 1)
st.session_state.df.index.name = "Row"

# --- Main Data Table ---
with st.expander("📝 ตารางข้อมูล (Data)", expanded=True):
    _cfg = {"_index": st.column_config.NumberColumn("Row", format="%d")}
    for _c in st.session_state.df.columns:
        if str(_c).lower() != "cavity" and pd.api.types.is_numeric_dtype(st.session_state.df[_c]):
            _cfg[_c] = st.column_config.NumberColumn(format="%.5f", step=0.00001)
    edited_df = st.data_editor(
        st.session_state.df, num_rows="dynamic", use_container_width=True,
        column_config=_cfg, key=f"data_editor_{st.session_state.editor_ver}"
    )
    edited_df.index = np.arange(1, len(edited_df) + 1)
    edited_df.index.name = "Row"

def to_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=True, sheet_name='Adjusted_Data')
    return output.getvalue()

st.sidebar.download_button("💾 เซฟข้อมูลเป็น Excel", data=to_excel(edited_df), file_name="data.xlsx", use_container_width=True)
st.sidebar.divider()

# --- Sidebar: 2. ตั้งค่า ---
st.sidebar.header("⚙️ ตั้งค่า (Settings)")
all_cols = edited_df.columns.tolist()
num_cols = [c for c in all_cols if str(c).lower() != "cavity"]

group_col = st.sidebar.selectbox("แบ่งกลุ่มตาม (Group by):", ["ไม่แบ่งกลุ่ม"] + all_cols, 
                                 index=all_cols.index("Cavity") + 1 if "Cavity" in all_cols else 0)

cavity_filter = "ทั้งหมด (Combined)"
if group_col != "ไม่แบ่งกลุ่ม" and group_col in edited_df.columns:
    unique_cavities = ["ทั้งหมด (Combined)"] + list(edited_df[group_col].dropna().unique())
    cavity_filter = st.sidebar.selectbox("เลือกกลุ่ม (Filter):", unique_cavities)

view_mode = st.sidebar.radio("รูปแบบการดู:", ["🔍 ดูทีละกราฟ", "📜 ดูทั้งหมด"], horizontal=True)

if "ดูทีละกราฟ" in view_mode:
    selected_col = st.sidebar.selectbox("พอยต์ที่ต้องการดู:", num_cols)
    auto_lsl, auto_target, auto_usl = parse_spec_from_col(selected_col)
    c1, c2, c3 = st.sidebar.columns(3)
    lsl_input = c1.number_input("LSL", value=auto_lsl, format="%.4f", step=0.0001)
    target_input = c2.number_input("Target", value=auto_target, format="%.4f", step=0.0001)
    usl_input = c3.number_input("USL", value=auto_usl, format="%.4f", step=0.0001)
    cols_to_plot = [selected_col]
else:
    cols_to_plot = st.sidebar.multiselect("พอยต์ที่จะแสดง:", num_cols, default=num_cols)

subgroup_size = st.sidebar.number_input("Subgroup size", min_value=1, value=32, step=1, help="สำหรับคำนวณ StDev Within แบบ Minitab")

# --- Sidebar: 3. ตกแต่ง & Export ---
with st.sidebar.expander("🎨 ตกแต่ง & ดาวน์โหลดกราฟ"):
    c_c1, c_c2 = st.columns(2)
    box_fill_hex = c_c1.color_picker("สีกล่อง", "#72A0E5")
    box_line_hex = c_c2.color_picker("สีเส้น", "#333333")
    box_width_val = st.slider("ความกว้างกล่อง", 0.1, 0.7, 0.35, 0.05)
    box_gap_val = st.slider("ระยะห่างกล่อง", 0.3, 2.5, 1.0, 0.1)
    chart_height = st.slider("ความสูงกราฟ", 380, 700, 480, 20)
    
    st.divider()
    st.markdown("**ดาวน์โหลดรูปภาพ**")
    EXPORT_TYPES = ["Boxplot", "Process Capability", "Probability Plot"]
    export_cols = st.multiselect("พอยต์:", num_cols, default=num_cols[:1])
    export_types = st.multiselect("กราฟ:", EXPORT_TYPES, default=EXPORT_TYPES)
    
    ec1, ec2 = st.columns(2)
    with ec1:
        export_w = st.number_input("กว้าง (px)", min_value=300, max_value=1600, value=600, step=50)
    with ec2:
        export_h = st.number_input("สูง (px)", min_value=300, max_value=1200, value=480, step=20)
    
    if st.button("🖼️ สร้างไฟล์ ZIP", use_container_width=True):
        if not export_cols or not export_types:
            st.warning("เลือกพอยต์และชนิดกราฟอย่างน้อยอย่างละ 1")
        else:
            try:
                with st.spinner(f"กำลังสร้างรูป {len(export_cols)} พอยต์..."):
                    st.session_state.export_zips = build_export_zips(
                        export_cols, export_types, int(export_w), int(export_h))
            except Exception as e:
                st.session_state.pop("export_zips", None)
                st.error(f"สร้างรูปไม่สำเร็จ: {e}\n\nลอง: pip install kaleido==0.2.1 plotly==5.24.1")
    
    if "export_zips" in st.session_state:
        for _t_name, _bytes in st.session_state.export_zips.items():
            _fname = "all_charts.zip" if _t_name == "ทั้งหมด" else f"{EXPORT_FILE.get(_t_name, 'charts')}.zip"
            st.download_button(f"⬇️ {_t_name} (.zip)", data=_bytes, file_name=_fname,
                               mime="application/zip", use_container_width=True, key=f"dl_{_t_name}")

def get_filtered_data(df_in, col_name, grp_col, cav_val):
    temp_df = df_in[[col_name] + ([grp_col] if grp_col != "ไม่แบ่งกลุ่ม" else [])].copy()
    temp_df["Row_ID"] = temp_df.index
    temp_df[col_name] = pd.to_numeric(temp_df[col_name], errors='coerce')
    temp_df = temp_df.dropna(subset=[col_name])
    if grp_col != "ไม่แบ่งกลุ่ม" and cav_val != "ทั้งหมด (Combined)":
        temp_df = temp_df[temp_df[grp_col].astype(str) == str(cav_val)]
    return temp_df

# ==============================================================================
# กราฟฟังก์ชัน
# ==============================================================================
def create_boxplot(df_in, col_name, grp_col, lsl, target, usl):
    valid_df = df_in[[col_name] + ([grp_col] if grp_col != "ไม่แบ่งกลุ่ม" else [])].dropna(subset=[col_name]).copy()
    valid_df["Row_ID"] = valid_df.index
    valid_df[col_name] = pd.to_numeric(valid_df[col_name], errors='coerce')
    valid_df = valid_df.dropna(subset=[col_name])

    fig = go.Figure()
    fill_rgba = hex_to_rgba(box_fill_hex, 0.85)
    tick_pos, tick_txt = [], []
    n_g = valid_df[grp_col].nunique() if grp_col != "ไม่แบ่งกลุ่ม" else 1
    bw = min(box_width_val, box_gap_val * 0.95) if n_g > 1 else box_width_val

    if grp_col != "ไม่แบ่งกลุ่ม":
        for gi, (grp, grp_df) in enumerate(valid_df.groupby(grp_col)):
            pos = gi * box_gap_val
            tick_pos.append(pos)
            tick_txt.append(str(grp))
            fig.add_trace(go.Box(x=[pos]*len(grp_df), y=grp_df[col_name], width=bw, boxpoints='outliers', customdata=grp_df["Row_ID"],
                                 hovertemplate="Row: %{customdata}<br>Value: %{y:.5f}<extra></extra>", fillcolor=fill_rgba,
                                 line=dict(color=box_line_hex, width=1.5), marker=dict(color="red", size=7, symbol="asterisk")))
    else:
        tick_pos, tick_txt = [0], [col_name]
        fig.add_trace(go.Box(x=[0]*len(valid_df), y=valid_df[col_name], width=bw, boxpoints='outliers', customdata=valid_df["Row_ID"],
                             hovertemplate="Row: %{customdata}<br>Value: %{y:.5f}<extra></extra>", fillcolor=fill_rgba,
                             line=dict(color=box_line_hex, width=1.5), marker=dict(color="red", size=7, symbol="asterisk")))

    for val, col in [(usl, "red"), (target, "limegreen"), (lsl, "red")]:
        fig.add_hline(y=val, line_dash="dash", line_color=col, line_width=1.5, annotation_text=f" {val}", annotation_position="right")

    y_min = min(lsl, valid_df[col_name].min()) if len(valid_df) > 0 else lsl
    y_max = max(usl, valid_df[col_name].max()) if len(valid_df) > 0 else usl
    span = y_max - y_min if y_max > y_min else 0.003
    n_b = len(tick_pos)
    x_span = max((n_b - 1) * box_gap_val + 1.0, 2.0) if n_b > 1 else 1.0
    x_mid = (tick_pos[0] + tick_pos[-1]) / 2 if n_b > 0 else 0

    fig.update_layout(title=dict(text=f"<b>Boxplot: {col_name}</b>", x=0.5),
                      yaxis=dict(range=[y_min - span*0.12, y_max + span*0.12], tickformat=".4f", zeroline=False),
                      xaxis=dict(tickmode='array', tickvals=tick_pos, ticktext=tick_txt, range=[x_mid - x_span/2, x_mid + x_span/2]),
                      plot_bgcolor="white", height=chart_height, margin=dict(l=50, r=50, t=50, b=40), showlegend=False)
    fig.update_xaxes(showline=True, linewidth=1, linecolor='#CCC', mirror=True)
    fig.update_yaxes(showline=True, linewidth=1, linecolor='#CCC', mirror=True, gridcolor="#EAEAEA")
    return fig

def create_capability(df_in, col_name, grp_col, cav_val, lsl, target, usl, subgroup_size=1):
    valid_df = get_filtered_data(df_in, col_name, grp_col, cav_val)
    data = valid_df[col_name]
    n = len(data)
    if n == 0: return None, {}
    mean, std_overall = data.mean(), data.std(ddof=1) if n > 1 else 0.0001
    std_within = calc_within(data.values, subgroup_size)
    if not np.isfinite(std_within) or std_within <= 0: std_within = std_overall

    pp = (usl - lsl) / (6 * std_overall) if std_overall > 0 else 0
    ppl, ppu = (mean - lsl)/(3*std_overall), (usl - mean)/(3*std_overall)
    s_t = np.sqrt(((data - target) ** 2).sum() / n) if n > 0 else 0
    cpm = min(usl - target, target - lsl) / (3 * s_t) if s_t > 0 else 0
    cp = (usl - lsl) / (6 * std_within) if std_within > 0 else 0
    cpl, cpu = (mean - lsl)/(3*std_within), (usl - mean)/(3*std_within)

    ax_lo, ax_hi = min(lsl, float(data.min())), max(usl, float(data.max()))
    span = ax_hi - ax_lo if ax_hi > ax_lo else 0.003
    step = span / 8
    t0 = np.ceil(ax_lo / step - 1e-9) * step
    
    BIN_DIV = 8
    bin_w = step / BIN_DIV
    b_start = t0 - bin_w / 2
    b_start += np.floor((float(data.min()) - b_start) / bin_w) * bin_w
    b_end = b_start + bin_w * (np.floor((float(data.max()) - b_start) / bin_w) + 1)
    
    # คำนวณความสูงสูงสุดของแกน Y เพื่อให้ฐานกราฟติดขอบล่างพอดี
    max_y_density = 0
    if std_overall > 0: max_y_density = max(max_y_density, stats.norm.pdf(mean, mean, std_overall))
    if std_within > 0: max_y_density = max(max_y_density, stats.norm.pdf(mean, mean, std_within))
    if n > 0 and bin_w > 0:
        counts, _ = np.histogram(data, bins=np.arange(b_start, b_end + bin_w, bin_w))
        if len(counts) > 0:
            max_y_density = max(max_y_density, (counts / (n * bin_w)).max())
            
    fig = go.Figure()
    fig.add_trace(go.Histogram(x=data, histnorm='probability density', showlegend=False,
                               xbins=dict(start=b_start, end=b_end, size=bin_w),
                               marker_color="#7DA6D9", marker_line=dict(color="#1F3E7A", width=0.8)))
    
    x_grid = np.linspace(ax_lo - span*0.2, ax_hi + span*0.2, 400)
    fig.add_trace(go.Scatter(x=x_grid, y=stats.norm.pdf(x_grid, mean, std_overall), mode='lines', line=dict(color="#8B1A1A", width=1.8)))
    fig.add_trace(go.Scatter(x=x_grid, y=stats.norm.pdf(x_grid, mean, std_within), mode='lines', line=dict(color="#555", width=1.8, dash='dash')))

    PLOT_TOP = 0.865
    for val, col, txt in [(usl, "#8B1A1A", "USL"), (target, "#0B6623", "Target"), (lsl, "#8B1A1A", "LSL")]:
        fig.add_vline(x=val, line_dash="dash", line_color=col, line_width=1.2)
        fig.add_annotation(x=val, xref="x", y=PLOT_TOP, yref="paper", text=txt, showarrow=False,
                           yanchor="bottom", yshift=3, font=dict(color=col, size=15, family="Segoe UI, Arial, sans-serif"))

    def _t(x, y, text, anchor="left", size=14, italic=False, bold=False):
        txt = f"<b>{text}</b>" if bold else text
        txt = f"<i>{txt}</i>" if italic else txt
        fig.add_annotation(x=x, y=y, xref="paper", yref="paper", text=txt, showarrow=False,
                           xanchor=anchor, yanchor="middle", font=dict(size=size, color="#222222", family="Segoe UI, Arial, sans-serif"))

    # เอา (Cavity: X) ออกจาก Title
    _t(0.5, 0.955, f"Process Capability Report for {col_name}", "center", 24)

    _t(0.155, 0.838, "Process Data", "center")
    for yy, (lb, vv) in zip(
        [0.812, 0.784, 0.758, 0.730, 0.702, 0.673, 0.646],
        [("LSL", fmt6(lsl)), ("Target", fmt6(target)), ("USL", fmt6(usl)), ("Sample Mean", fmt6(mean)),
         ("Sample N", f"{n}"), ("StDev(Overall)", fmt6(std_overall)), ("StDev(Within)", fmt6(std_within))]):
        _t(0.03, yy, lb)
        _t(0.152, yy, vv)

    fig.add_shape(type="line", xref="paper", yref="paper", x0=0.748, x1=0.800, y0=0.840, y1=0.840, line=dict(color="#8B1A1A", width=2))
    fig.add_shape(type="line", xref="paper", yref="paper", x0=0.748, x1=0.800, y0=0.812, y1=0.812, line=dict(color="#555", width=2, dash="dash"))
    _t(0.809, 0.840, "Overall")
    _t(0.809, 0.812, "Within")

    _t(0.863, 0.759, "Overall Capability", "center")
    for yy, (lb, vv) in zip([0.731, 0.705, 0.677, 0.649, 0.621], [("Pp", pp), ("PPL", ppl), ("PPU", ppu), ("Ppk", ppk), ("Cpm", cpm)]):
        _t(0.815, yy, lb)
        _t(0.878, yy, f"{vv:.2f}")
        
    _t(0.862, 0.586, "Potential (Within) Capability", "center")
    for yy, (lb, vv) in zip([0.552, 0.524, 0.496, 0.468], [("Cp", cp), ("CPL", cpl), ("CPU", cpu), ("Cpk", cpk)]):
        _t(0.815, yy, lb)
        _t(0.878, yy, f"{vv:.2f}")

    obs_below, obs_above = (data < lsl).sum() / n * 1e6 if n > 0 else 0, (data > usl).sum() / n * 1e6 if n > 0 else 0
    exp_bel_o, exp_abv_o = stats.norm.cdf(lsl, mean, std_overall) * 1e6 if std_overall > 0 else 0, (1 - stats.norm.cdf(usl, mean, std_overall)) * 1e6 if std_overall > 0 else 0
    exp_bel_w, exp_abv_w = stats.norm.cdf(lsl, mean, std_within) * 1e6 if std_within > 0 else 0, (1 - stats.norm.cdf(usl, mean, std_within)) * 1e6 if std_within > 0 else 0
    
    col_x = [0.2227, 0.381, 0.5346]
    _t(0.284, 0.216, "Performance", "center")
    for cx, hd in zip(col_x, ["Observed", "Expected Overall", "Expected Within"]):
        _t(cx, 0.189, hd, "right")
    perf_rows = [
        ("PPM < LSL", [obs_below, exp_bel_o, exp_bel_w], 0.162),
        ("PPM > USL", [obs_above, exp_abv_o, exp_abv_w], 0.134),
        ("PPM Total", [obs_below+obs_above, exp_bel_o+exp_abv_o, exp_bel_w+exp_abv_w], 0.107),
    ]
    for lb, vals, yy in perf_rows:
        _t(0.036, yy, lb)
        for cx, vv in zip(col_x, vals): _t(cx, yy, f"{vv:.2f}", "right")

    _t(0.02, 0.025, "The actual process spread is represented by 6 sigma.", "left", 17, italic=True)

    # ปรับแกน Y ให้ติดขอบล่าง และแกน X ให้มี Margin ด้านข้างเผื่อ LSL/USL
    fig.update_layout(
        xaxis=dict(domain=[0.306, 0.721], range=[ax_lo - span*0.12, ax_hi + span*0.12], tickmode='array', tickvals=ticks,
                   ticktext=[f"{t:.{dec}f}" for t in ticks], tickangle=-45, tickfont=dict(size=14, family="Segoe UI, Arial, sans-serif"),
                   showgrid=True, gridcolor="#E6E6E6", showline=True, linecolor="#888888", mirror=True),
        yaxis=dict(domain=[0.359, PLOT_TOP], range=[0, max_y_density * 1.05], showticklabels=False, showgrid=True, gridcolor="#E6E6E6",
                   zeroline=False, showline=True, linecolor="#888888", mirror=True, nticks=6),
        bargap=0, showlegend=False, plot_bgcolor="white", paper_bgcolor="#DDDDDD", height=720, margin=dict(l=0, r=0, t=0, b=0)
    )

    metrics = {"N": n, "Mean": mean, "StDev_O": std_overall, "StDev_W": std_within,
               "Cp": cp, "Cpk": min(cpl, cpu), "Pp": pp, "Ppk": min(ppl, ppu), "Cpm": cpm}
    return fig, metrics

def create_prob_plot(df_in, col_name, grp_col, cav_val):
    valid_df = get_filtered_data(df_in, col_name, grp_col, cav_val)
    data = valid_df[col_name]
    n = len(data)
    if n < 3: return None, 1.0, 1.0, 0, 0, n

    mean, std_overall = data.mean(), data.std(ddof=1) if n > 1 else 0.0001
    ad_stat = stats.anderson(data, dist='norm').statistic
    ad_star = ad_stat * (1 + 0.75/n + 2.25/(n**2))
    
    if ad_star >= 0.6: ad_pval = np.exp(1.2937 - 5.709*ad_star + 0.0186*(ad_star**2))
    elif ad_star >= 0.34: ad_pval = np.exp(0.9177 - 4.279*ad_star - 1.38*(ad_star**2))
    elif ad_star > 0.2: ad_pval = 1 - np.exp(-8.318 + 42.796*ad_star - 59.938*(ad_star**2))
    else: ad_pval = 1 - np.exp(-13.436 + 101.14*ad_star - 223.73*(ad_star**2))
    ad_pval = float(np.clip(ad_pval, 0.0001, 0.9999))

    sorted_df = valid_df.sort_values(by=col_name).reset_index(drop=True)
    probs = (np.arange(1, n + 1) - 0.3) / (n + 0.4) * 100
    z_scores = stats.norm.ppf(probs / 100.0)

    tick_p = [0.1, 1, 5, 10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 99, 99.9]
    tick_z = stats.norm.ppf(np.array(tick_p) / 100.0)

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=sorted_df[col_name], y=z_scores, mode='markers',
                             customdata=np.stack((sorted_df["Row_ID"], probs), axis=-1),
                             hovertemplate="Row: %{customdata[0]}<br>Value: %{x:.5f}<extra></extra>",
                             marker=dict(size=8, color=box_fill_hex, line=dict(width=1, color=box_line_hex))))
    fig.add_trace(go.Scatter(x=mean + z_scores * std_overall, y=z_scores, mode='lines', line=dict(color='darkred', width=1.5)))

    # เอา (Cavity: X) ออกจาก Title
    fig.update_layout(title=dict(text=f"<b>Probability Plot of {col_name}</b><br><sup>AD = {ad_stat:.3f}, P-Value = {ad_pval:.4f}</sup>", x=0.5),
                      yaxis=dict(title="Percent", tickmode='array', tickvals=tick_z, ticktext=[str(p) for p in tick_p]),
                      plot_bgcolor="white", height=chart_height, margin=dict(l=50, r=40, t=65, b=40), showlegend=False)
    fig.update_xaxes(showline=True, linewidth=1, linecolor='#CCC', mirror=True, gridcolor="#EAEAEA")
    fig.update_yaxes(showline=True, linewidth=1, linecolor='#CCC', mirror=True, gridcolor="#EAEAEA")
    return fig, ad_stat, ad_pval, mean, std_overall, n

def diagnose_capability(data, lsl, target, usl, subgroup_size=1):
    x = np.asarray(data, dtype=float)
    n = len(x)
    mean = x.mean()
    s = x.std(ddof=1)
    dx = np.diff(x)
    mr = np.abs(dx)

    cands = {
        "Average MR: MRbar/1.128 (w=2)": mr.mean() / 1.128,
        "Median MR: MR-median/0.954 (w=2)": np.median(mr) / 0.954,
        "Sqrt of MSSD: sqrt(Σ(Δx)²/(2(n-1)))": np.sqrt((dx ** 2).sum() / (2 * (n - 1))),
        "StDev Overall (s)": s,
    }
    if subgroup_size > 1:
        groups = [x[i:i + subgroup_size] for i in range(0, n, subgroup_size)]
        groups = [g for g in groups if len(g) > 1]
        if groups:
            ss = sum(((g - g.mean()) ** 2).sum() for g in groups)
            d = sum(len(g) - 1 for g in groups)
            sp = np.sqrt(ss / d)
            cands[f"Pooled StDev (size={subgroup_size}) ไม่หาร c4"] = sp
            cands[f"Pooled StDev (size={subgroup_size}) หาร c4(d+1)"] = sp / c4(d + 1)

    rows = []
    for name, sg in cands.items():
        if not np.isfinite(sg) or sg <= 0:
            continue
        cpl = (mean - lsl) / (3 * sg)
        cpu = (usl - mean) / (3 * sg)
        rows.append({
            "วิธีประมาณ σ": name, "StDev(Within)": f"{sg:.7f}",
            "Cp": f"{(usl - lsl) / (6 * sg):.4f}", "CPL": f"{cpl:.4f}",
            "CPU": f"{cpu:.4f}", "Cpk": f"{min(cpl, cpu):.4f}"
        })

    half = min(usl - target, target - lsl)
    ss_t = ((x - target) ** 2).sum()
    cpm_rows = []
    for name, val in {
        "min(USL-T, T-LSL) / (3·sqrt(Σ(x-T)²/(n-1)))": half / (3 * np.sqrt(ss_t / (n - 1))),
        "(USL-LSL) / (6·sqrt(s² + (mean-T)²))": (usl - lsl) / (6 * np.sqrt(s ** 2 + (mean - target) ** 2)),
        "(USL-LSL) / (6·sqrt(Σ(x-T)²/n))": (usl - lsl) / (6 * np.sqrt(ss_t / n)),
    }.items():
        cpm_rows.append({"สูตร Cpm": name, "Cpm": f"{val:.4f}"})
    return pd.DataFrame(rows), pd.DataFrame(cpm_rows)

# ==============================================================================
# Export กราฟ 
# ==============================================================================
EXPORT_TYPES = ["Boxplot", "Process Capability", "Probability Plot"]
EXPORT_FILE = {"Boxplot": "boxplot", "Process Capability": "process_capability", "Probability Plot": "probability_plot"}

def build_export_zips(points, types, img_w, img_h):
    cav_tag = "" if cavity_filter == "ทั้งหมด (Combined)" else f"_Cavity{cavity_filter}"
    files = {t: [] for t in types}
    for i, col_name in enumerate(points, 1):
        if "ดูทีละกราฟ" in view_mode and col_name == selected_col:
            c_lsl, c_target, c_usl = lsl_input, target_input, usl_input
        else:
            c_lsl, c_target, c_usl = parse_spec_from_col(col_name)
        safe = re.sub(r"[^0-9A-Za-z._-]+", "_", str(col_name)).strip("_")
        base = f"{i:02d}_{safe}{cav_tag}"

        if "Boxplot" in types:
            f = create_boxplot(edited_df, col_name, group_col, c_lsl, c_target, c_usl)
            files["Boxplot"].append((f"{base}_boxplot.png", f.to_image(format="png", width=img_w, height=img_h, scale=2)))
        if "Process Capability" in types:
            f, _m = create_capability(edited_df, col_name, group_col, cavity_filter, c_lsl, c_target, c_usl, subgroup_size)
            if f is not None:
                files["Process Capability"].append((f"{base}_capability.png", f.to_image(format="png", width=1000, height=720, scale=2)))
        if "Probability Plot" in types:
            f = create_prob_plot(edited_df, col_name, group_col, cavity_filter)[0]
            if f is not None:
                files["Probability Plot"].append((f"{base}_probplot.png", f.to_image(format="png", width=img_w, height=img_h, scale=2)))

    zips = {}
    for t, items in files.items():
        buf = BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, b in items: zf.writestr(name, b)
        zips[t] = buf.getvalue()
    if len(types) > 1:
        buf = BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for t, items in files.items():
                for name, b in items: zf.writestr(f"{EXPORT_FILE[t]}/{name}", b)
        zips["ทั้งหมด"] = buf.getvalue()
    return zips

# ==============================================================================
# แสดงผล (Tabs)
# ==============================================================================
t1, t2, t3 = st.tabs(["📦 Boxplot", "📈 Process Capability", "🎯 Probability Plot"])

with t1:
    if "ดูทีละกราฟ" in view_mode:
        c_left, c_center, c_right = st.columns([1, 2.2, 1])
        with c_center:
            fig_b = create_boxplot(edited_df, selected_col, group_col, lsl_input, target_input, usl_input)
            st.plotly_chart(fig_b, use_container_width=True)
    else:
        grid_cols = st.columns(2)
        for idx, col_name in enumerate(cols_to_plot):
            c_lsl, c_target, c_usl = parse_spec_from_col(col_name)
            with grid_cols[idx % 2]:
                fig_b = create_boxplot(edited_df, col_name, group_col, c_lsl, c_target, c_usl)
                st.plotly_chart(fig_b, use_container_width=True)

with t2:
    if "ดูทีละกราฟ" in view_mode:
        fig_c, m = create_capability(edited_df, selected_col, group_col, cavity_filter,
                                     lsl_input, target_input, usl_input, subgroup_size)
        if m:
            st.plotly_chart(fig_c, use_container_width=True)
            with st.expander("🔬 วินิจฉัย: เทียบกับค่าใน Minitab (เปิดดูวิธีที่ตรงกัน)", expanded=False):
                _d = get_filtered_data(edited_df, selected_col, group_col, cavity_filter)[selected_col]
                _w_df, _cpm_df = diagnose_capability(_d.values, lsl_input, target_input, usl_input, subgroup_size)
                st.caption(f"N = {len(_d)} | Mean = {_d.mean():.7f} | LSL/T/USL = {lsl_input} / {target_input} / {usl_input}")
                st.dataframe(_w_df.set_index("วิธีประมาณ σ"), use_container_width=True)
                st.dataframe(_cpm_df.set_index("สูตร Cpm"), use_container_width=True)
        else:
            st.warning("ข้อมูลไม่เพียงพอสำหรับการคำนวณในกลุ่มที่เลือก")
    else:
        grid_cols = st.columns(1)
        for idx, col_name in enumerate(cols_to_plot):
            c_lsl, c_target, c_usl = parse_spec_from_col(col_name)
            fig_c, m = create_capability(edited_df, col_name, group_col, cavity_filter,
                                         c_lsl, c_target, c_usl, subgroup_size)
            if m:
                with grid_cols[0]:
                    st.plotly_chart(fig_c, use_container_width=True)
                    st.divider()

with t3:
    if "ดูทีละกราฟ" in view_mode:
        fig_p, ad_stat, ad_pval, mean, std, n = create_prob_plot(edited_df, selected_col, group_col, cavity_filter)
        if n >= 3:
            c1, c2 = st.columns([2.5, 1])
            with c1:
                event = st.plotly_chart(fig_p, use_container_width=True, on_select="rerun",
                                        selection_mode="points", key=f"prob_plot_single_{st.session_state.editor_ver}")
            with c2:
                st.markdown("##### 🎯 Normality Test")
                if ad_pval >= 0.05: st.success(f"✅ **Normal Distribution**\n\n(P-Value = {ad_pval:.4f} ≥ 0.05)")
                else: st.error(f"❌ **Non-Normal**\n\n(P-Value = {ad_pval:.4f} < 0.05)")
                st.metric("P-Value (Anderson-Darling)", f"{ad_pval:.4f}")
                st.metric("AD Statistic", f"{ad_stat:.3f}")
                st.metric("Mean / StDev", f"{mean:.5f} / {std:.6f}")
                st.info("💡 **ทริค:** คลิกจุดบนกราฟ (กด Shift ค้างเพื่อเลือกหลายจุด) แล้วใส่ค่าใหม่ในช่องด้านล่าง กดอัปเดต ค่าจะไปแก้ในตารางด้านบนให้ทันที")

            try: _pts = event["selection"]["points"]
            except Exception: _pts = []
            _sd = get_filtered_data(edited_df, selected_col, group_col, cavity_filter)
            _sd = _sd.sort_values(by=selected_col).reset_index(drop=True)
            _sel_ids = []
            for _p in _pts:
                if _p.get("curve_number", 0) != 0: continue
                _i = _p.get("point_index", _p.get("point_number"))
                if _i is not None and 0 <= int(_i) < len(_sd):
                    _rid = int(_sd.loc[int(_i), "Row_ID"])
                    if _rid not in _sel_ids: _sel_ids.append(_rid)

            if _sel_ids:
                st.markdown("##### ✏️ แก้ค่าจุดที่เลือก")
                _new_vals = {}
                _ecols = st.columns(min(len(_sel_ids), 4))
                for _k, _rid in enumerate(_sel_ids[:8]):
                    _cur = float(edited_df.loc[_rid, selected_col])
                    with _ecols[_k % len(_ecols)]:
                        _new_vals[_rid] = st.number_input(f"Row #{_rid}", value=_cur, format="%.5f", step=0.00001,
                                                          key=f"newval_{selected_col}_{_rid}_{st.session_state.editor_ver}")
                if st.button("✅ อัปเดตค่าลงตาราง", type="primary"):
                    _new_df = edited_df.copy()
                    for _rid, _v in _new_vals.items(): _new_df.loc[_rid, selected_col] = _v
                    st.session_state.df = _new_df
                    st.session_state.editor_ver += 1
                    st.rerun()
        else:
            st.warning("ข้อมูลน้อยเกินไปสำหรับการรัน Probability Plot (ต้องการอย่างน้อย 3 แถว)")
    else:
        grid_cols = st.columns(2)
        for idx, col_name in enumerate(cols_to_plot):
            fig_p, ad_stat, ad_pval, mean, std, n = create_prob_plot(edited_df, col_name, group_col, cavity_filter)
            if n >= 3:
                with grid_cols[idx % 2]:
                    st.plotly_chart(fig_p, use_container_width=True)
