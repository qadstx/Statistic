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
    if st.button("🖼️ สร้างไฟล์ ZIP", use_container_width=True):
        st.info("กำลังสร้างรูปภาพ... (ฟังก์ชันนี้ต้องติดตั้ง kaleido และ plotly)")
        # หมายเหตุ: นำฟังก์ชัน build_export_zips มาวางตรงนี้ได้ถ้าต้องการเปิดใช้งานสมบูรณ์

def get_filtered_data(df_in, col_name, grp_col, cav_val):
    temp_df = df_in[[col_name] + ([grp_col] if grp_col != "ไม่แบ่งกลุ่ม" else [])].copy()
    temp_df["Row_ID"] = temp_df.index
    temp_df[col_name] = pd.to_numeric(temp_df[col_name], errors='coerce')
    temp_df = temp_df.dropna(subset=[col_name])
    if grp_col != "ไม่แบ่งกลุ่ม" and cav_val != "ทั้งหมด (Combined)":
        temp_df = temp_df[temp_df[grp_col].astype(str) == str(cav_val)]
    return temp_df

# ==============================================================================
# กราฟฟังก์ชัน (ย่อให้กระชับ)
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
    b_start = t0 - step/2
    b_start += np.floor((float(data.min()) - b_start) / step) * step
    
    fig = go.Figure()
    fig.add_trace(go.Histogram(x=data, histnorm='probability density', xbins=dict(start=b_start, size=step),
                               marker_color="#7DA6D9", marker_line=dict(color="#1F3E7A", width=0.8)))
    
    x_grid = np.linspace(ax_lo, ax_hi, 400)
    fig.add_trace(go.Scatter(x=x_grid, y=stats.norm.pdf(x_grid, mean, std_overall), mode='lines', line=dict(color="#8B1A1A", width=1.8)))
    fig.add_trace(go.Scatter(x=x_grid, y=stats.norm.pdf(x_grid, mean, std_within), mode='lines', line=dict(color="#555", width=1.8, dash='dash')))

    for val, col in [(usl, "#8B1A1A"), (target, "#0B6623"), (lsl, "#8B1A1A")]:
        fig.add_vline(x=val, line_dash="dash", line_color=col, line_width=1.2)

    title_sfx = f" (Group: {cav_val})" if cav_val != "ทั้งหมด (Combined)" else ""
    fig.update_layout(title=dict(text=f"<b>Process Capability: {col_name}{title_sfx}</b>", x=0.5),
                      xaxis=dict(range=[ax_lo - span*0.1, ax_hi + span*0.1], tickformat=".4f"),
                      yaxis=dict(showticklabels=False), plot_bgcolor="white", height=chart_height,
                      margin=dict(l=40, r=40, t=50, b=40), showlegend=False)
    fig.update_xaxes(showline=True, linewidth=1, linecolor='#CCC', mirror=True, gridcolor="#EAEAEA")
    
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

    fig.update_layout(title=dict(text=f"<b>Probability Plot: {col_name}</b><br><sup>AD = {ad_stat:.3f}, P-Value = {ad_pval:.4f}</sup>", x=0.5),
                      yaxis=dict(title="Percent", tickmode='array', tickvals=tick_z, ticktext=[str(p) for p in tick_p]),
                      plot_bgcolor="white", height=chart_height, margin=dict(l=50, r=40, t=65, b=40), showlegend=False)
    fig.update_xaxes(showline=True, linewidth=1, linecolor='#CCC', mirror=True, gridcolor="#EAEAEA")
    fig.update_yaxes(showline=True, linewidth=1, linecolor='#CCC', mirror=True, gridcolor="#EAEAEA")
    return fig, ad_stat, ad_pval, mean, std_overall, n

# ==============================================================================
# แสดงผล
# ==============================================================================
t1, t2, t3 = st.tabs(["📦 Boxplot", "📈 Capability", "🎯 Probability Plot"])

with t1:
    if "ดูทีละกราฟ" in view_mode:
        c1, c2, c3 = st.columns([1, 2, 1])
        with c2: st.plotly_chart(create_boxplot(edited_df, selected_col, group_col, lsl_input, target_input, usl_input), use_container_width=True)
    else:
        g = st.columns(2)
        for i, c in enumerate(cols_to_plot):
            ls, tg, us = parse_spec_from_col(c)
            with g[i%2]: st.plotly_chart(create_boxplot(edited_df, c, group_col, ls, tg, us), use_container_width=True)

with t2:
    if "ดูทีละกราฟ" in view_mode:
        fig_c, m = create_capability(edited_df, selected_col, group_col, cavity_filter, lsl_input, target_input, usl_input, subgroup_size)
        if m:
            c1, c2, c3 = st.columns([1.2, 2.5, 1])
            c1.markdown("##### 📊 ข้อมูล (Data)")
            c1.dataframe(pd.DataFrame({"Metric": ["Mean", "N", "StDev(Overall)", "StDev(Within)"], 
                                       "Value": [f"{m['Mean']:.5f}", m['N'], f"{m['StDev_O']:.6f}", f"{m['StDev_W']:.6f}"]}).set_index("Metric"), use_container_width=True)
            c2.plotly_chart(fig_c, use_container_width=True)
            c3.markdown("##### 🏆 ดัชนี (Indices)")
            c3.dataframe(pd.DataFrame({"Index": ["Cp", "Cpk", "Pp", "Ppk", "Cpm"], 
                                       "Value": [f"{m['Cp']:.2f}", f"{m['Cpk']:.2f}", f"{m['Pp']:.2f}", f"{m['Ppk']:.2f}", f"{m['Cpm']:.2f}"]}).set_index("Index"), use_container_width=True)
    else:
        g = st.columns(2)
        for i, c in enumerate(cols_to_plot):
            ls, tg, us = parse_spec_from_col(c)
            fig_c, m = create_capability(edited_df, c, group_col, cavity_filter, ls, tg, us, subgroup_size)
            if m:
                with g[i%2]:
                    st.plotly_chart(fig_c, use_container_width=True)
                    st.caption(f"**{c}** | Cp: `{m['Cp']:.2f}` | Cpk: `{m['Cpk']:.2f}` | Ppk: `{m['Ppk']:.2f}`")

with t3:
    if "ดูทีละกราฟ" in view_mode:
        fig_p, ad, pval, mn, sd, n = create_prob_plot(edited_df, selected_col, group_col, cavity_filter)
        if n >= 3:
            c1, c2 = st.columns([2.5, 1])
            c1.plotly_chart(fig_p, use_container_width=True)
            c2.markdown("##### 🎯 สรุปผล (Normality Test)")
            c2.success(f"✅ Normal (P = {pval:.3f})" if pval >= 0.05 else f"❌ Non-Normal (P = {pval:.3f})", icon="✅" if pval>=0.05 else "❌")
            c2.caption(f"AD: {ad:.3f} | Mean: {mn:.4f} | SD: {sd:.5f}")
            c2.info("💡 คลิกแก้ไขค่าที่หลุดกรอบ ในตารางด้านบนได้เลย กราฟจะอัปเดตทันที")
    else:
        g = st.columns(2)
        for i, c in enumerate(cols_to_plot):
            fig_p, ad, pval, mn, sd, n = create_prob_plot(edited_df, c, group_col, cavity_filter)
            if n >= 3:
                with g[i%2]: st.plotly_chart(fig_p, use_container_width=True)
