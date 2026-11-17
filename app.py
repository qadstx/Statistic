import streamlit as st
import pandas as pd
import numpy as np
from scipy import stats
import plotly.graph_objects as go
import matplotlib.pyplot as plt
import re
from io import BytesIO

st.set_page_config(page_title="Mini-QAD Statistical Tool", layout="wide")
st.title("📊 Minitab Alternative: Boxplot, Capability & Probability Plot")

# --- ฟังก์ชันดึงค่า Target / Tol จากชื่อคอลัมน์ เช่น B1_0.328 ± 0.0015 ---
def parse_spec_from_col(col_name):
    match = re.search(r"(\d+\.\d+)\s*[±\+\-]\s*(\d+\.\d+)", str(col_name))
    if match:
        target = float(match.group(1))
        tol = float(match.group(2))
        return round(target - tol, 6), target, round(target + tol, 6)
    return 0.3265, 0.3280, 0.3295  # ค่า Default กรณีชื่อไม่ได้ใส่สเปก

# --- 1. ส่วนจัดการข้อมูล (Upload หรือ ตารางเปล่าให้กรอก) ---
st.sidebar.header("📁 1. จัดการข้อมูล (Data Input)")
uploaded_file = st.sidebar.file_uploader("อัปโหลดไฟล์ Excel หรือ CSV", type=["xlsx", "csv"])

if "df" not in st.session_state:
    # สร้างข้อมูลตัวอย่างเริ่มต้นตามรูปของคุณ
    np.random.seed(42)
    st.session_state.df = pd.DataFrame({
        "B1_0.328 ± 0.0015": np.round(np.random.normal(0.3283, 0.00012, 32), 5),
        "B2_0.2845 ± 0.0015": np.round(np.random.normal(0.2843, 0.00012, 32), 5),
        "Cavity": [1]*16 + [2]*16
    })

if uploaded_file is not None:
    if st.sidebar.button("โหลดข้อมูลจากไฟล์"):
        if uploaded_file.name.endswith(".csv"):
            st.session_state.df = pd.read_csv(uploaded_file)
        else:
            st.session_state.df = pd.read_excel(uploaded_file)

if st.sidebar.button("🧹 ล้างตาราง (สร้างตารางเปล่า)"):
    st.session_state.df = pd.DataFrame({"Point_1": [np.nan]*10, "Cavity": [1]*10})

with st.expander("📝 ตารางข้อมูล (ดับเบิลคลิกแก้ไขตัวเลข / ก๊อปวางจาก Excel / เพิ่ม-ลบแถวได้ Real-time)", expanded=True):
    # แสดงเลข Row ชัดเจนเพื่อให้เทียบกับจุดบนกราฟได้ทันที
    edited_df = st.data_editor(
        st.session_state.df,
        num_rows="dynamic",
        use_container_width=True,
        key="data_editor"
    )

# ปุ่ม Save ข้อมูลที่ปรับแก้แล้วเป็น Excel
def to_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=True, sheet_name='Adjusted_Data')
    return output.getvalue()

st.sidebar.download_button(
    label="💾 เซฟตารางข้อมูลที่แก้แล้ว (.xlsx)",
    data=to_excel(edited_df),
    file_name="adjusted_data.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

# --- 2. ตั้งค่าการวิเคราะห์และ Spec Limits ---
st.sidebar.header("⚙️ 2. ตั้งค่าตัวแปรและ Spec")
all_cols = edited_df.columns.tolist()
num_cols = [c for c in all_cols if c.lower() != "cavity"]

selected_col = st.sidebar.selectbox("เลือกพอยต์ที่ต้องการวิเคราะห์ (Measurement)", num_cols)
group_col = st.sidebar.selectbox("เลือกคอลัมน์แยกกลุ่ม (เช่น Cavity)", ["ไม่แยกกลุ่ม"] + all_cols, 
                                 index=all_cols.index("Cavity")+1 if "Cavity" in all_cols else 0)

# ดึง Spec อัตโนมัติจากชื่อคอลัมน์ แต่ปรับแก้เองได้
auto_lsl, auto_target, auto_usl = parse_spec_from_col(selected_col)
lsl = st.sidebar.number_input("LSL (Lower Spec)", value=auto_lsl, format="%.5f", step=0.0001)
target = st.sidebar.number_input("Target (Nominal)", value=auto_target, format="%.5f", step=0.0001)
usl = st.sidebar.number_input("USL (Upper Spec)", value=auto_usl, format="%.5f", step=0.0001)

# เตรียมข้อมูลสำหรับคำนวณ
valid_df = edited_df[[selected_col] + ([group_col] if group_col != "ไม่แยกกลุ่ม" else [])].dropna(subset=[selected_col]).copy()
valid_df["Row_ID"] = valid_df.index + 1  # เก็บเลขบรรทัดที่แท้จริงไว้โชว์ตอนเอาเมาส์ชี้
data = pd.to_numeric(valid_df[selected_col], errors='coerce').dropna()

if len(data) > 2:
    tab1, tab2, tab3 = st.tabs(["📦 1. Boxplot (พร้อมเส้น Spec)", "📈 2. Process Capability (Histogram)", "🎯 3. Probability Plot (เช็ก P-value & จุดหลุด)"])

    # ================= TAB 1: BOXPLOT =================
    with tab1:
        fig_box = go.Figure()
        if group_col != "ไม่แยกกลุ่ม":
            for grp, grp_df in valid_df.groupby(group_col):
                fig_box.add_trace(go.Box(
                    y=grp_df[selected_col],
                    name=f"{group_col} {grp}",
                    boxpoints='outliers',
                    customdata=grp_df["Row_ID"],
                    hovertemplate="<b>Row: %{customdata}</b><br>Value: %{y:.5f}<extra></extra>",
                    fillcolor="rgba(114, 160, 229, 0.8)",
                    line=dict(color="rgb(50, 50, 50)")
                ))
        else:
            fig_box.add_trace(go.Box(
                y=valid_df[selected_col], name=selected_col, boxpoints='outliers',
                customdata=valid_df["Row_ID"],
                hovertemplate="<b>Row: %{customdata}</b><br>Value: %{y:.5f}<extra></extra>"
            ))

        # ตีเส้นประ USL / Target / LSL เหมือน Minitab
        fig_box.add_hline(y=usl, line_dash="dash", line_color="red", annotation_text=f"USL: {usl}", annotation_position="right")
        fig_box.add_hline(y=target, line_dash="dash", line_color="limegreen", annotation_text=f"Target: {target}", annotation_position="right")
        fig_box.add_hline(y=lsl, line_dash="dash", line_color="red", annotation_text=f"LSL: {lsl}", annotation_position="right")

        fig_box.update_layout(title=f"Boxplot of {selected_col}", xaxis_title=group_col, yaxis_title=selected_col, height=550)
        st.plotly_chart(fig_box, use_container_width=True)

    # ================= TAB 2: PROCESS CAPABILITY =================
    with tab2:
        n = len(data)
        mean = data.mean()
        std_overall = data.std(ddof=1)
        # คำนวณ StDev(Within) จาก Moving Range เหมือน Minitab กรณี Subgroup=1
        mr = np.abs(np.diff(data))
        std_within = mr.mean() / 1.128 if len(mr) > 0 and mr.mean() > 0 else std_overall

        # คำนวณ Pp, Ppk, Cpm, Cp, Cpk
        pp = (usl - lsl) / (6 * std_overall)
        ppl = (mean - lsl) / (3 * std_overall)
        ppu = (usl - mean) / (3 * std_overall)
        ppk = min(ppl, ppu)
        cpm = (usl - lsl) / (6 * np.sqrt(std_overall**2 + (mean - target)**2))

        cp = (usl - lsl) / (6 * std_within)
        cpl = (mean - lsl) / (3 * std_within)
        cpu = (usl - mean) / (3 * std_within)
        cpk = min(cpl, cpu)

        col_l, col_m, col_r = st.columns([1.2, 2.6, 1.2])
        with col_l:
            st.markdown("#### Process Data")
            st.dataframe(pd.DataFrame({
                "Metric": ["LSL", "Target", "USL", "Sample Mean", "Sample N", "StDev(Overall)", "StDev(Within)"],
                "Value": [f"{lsl:.4f}", f"{target:.4f}", f"{usl:.4f}", f"{mean:.6f}", f"{n}", f"{std_overall:.7f}", f"{std_within:.7f}"]
            }).set_index("Metric"))

        with col_m:
            x_grid = np.linspace(min(lsl, data.min()) - 0.0003, max(usl, data.max()) + 0.0003, 300)
            fig_cap = go.Figure()
            fig_cap.add_trace(go.Histogram(x=data, histnorm='probability density', name='Data', marker_color='#72a0e5', opacity=0.75))
            fig_cap.add_trace(go.Scatter(x=x_grid, y=stats.norm.pdf(x_grid, mean, std_overall), mode='lines', name='Overall', line=dict(color='darkred', width=2)))
            fig_cap.add_trace(go.Scatter(x=x_grid, y=stats.norm.pdf(x_grid, mean, std_within), mode='lines', name='Within', line=dict(color='royalblue', width=2, dash='dash')))
            
            fig_cap.add_vline(x=lsl, line_dash="dash", line_color="red", annotation_text="LSL")
            fig_cap.add_vline(x=target, line_dash="dash", line_color="green", annotation_text="Target")
            fig_cap.add_vline(x=usl, line_dash="dash", line_color="red", annotation_text="USL")
            fig_cap.update_layout(title=f"Process Capability Report for {selected_col}", height=480)
            st.plotly_chart(fig_cap, use_container_width=True)

        with col_r:
            st.markdown("#### Capability Indices")
            st.dataframe(pd.DataFrame({
                "Index": ["Pp", "PPL", "PPU", "Ppk", "Cpm", "---", "Cp", "CPL", "CPU", "Cpk"],
                "Value": [f"{pp:.2f}", f"{ppl:.2f}", f"{ppu:.2f}", f"{ppk:.2f}", f"{cpm:.2f}", "", f"{cp:.2f}", f"{cpl:.2f}", f"{cpu:.2f}", f"{cpk:.2f}"]
            }).set_index("Index"))

    # ================= TAB 3: PROBABILITY PLOT =================
    with tab3:
        # คำนวณ Anderson-Darling & Shapiro-Wilk Normality Test
        ad_res = stats.anderson(data, dist='norm')
        ad_stat = ad_res.statistic
        # สูตรคำนวณ P-value ของ Anderson-Darling ตามมาตรฐาน Minitab (D'Agostino & Stephens)
        ad_star = ad_stat * (1 + 0.75/n + 2.25/(n**2))
        if ad_star >= 0.6:
            ad_pval = np.exp(1.2937 - 5.709*ad_star + 0.0186*(ad_star**2))
        elif ad_star >= 0.34:
            ad_pval = np.exp(0.9177 - 4.279*ad_star - 1.38*(ad_star**2))
        elif ad_star > 0.2:
            ad_pval = 1 - np.exp(-8.318 + 42.796*ad_star - 59.938*(ad_star**2))
        else:
            ad_pval = 1 - np.exp(-13.436 + 101.14*ad_star - 223.73*(ad_star**2))
        
        shapiro_stat, shapiro_pval = stats.shapiro(data)

        # เรียงข้อมูลเพื่อพล็อต Probability Scale (1% - 99%)
        sorted_df = valid_df.sort_values(by=selected_col).reset_index(drop=True)
        # Median Ranks (Benard's approximation เหมือน Minitab)
        probs = (np.arange(1, n + 1) - 0.3) / (n + 0.4) * 100
        z_scores = stats.norm.ppf(probs / 100.0)
        
        # เส้นตรง Theoretical Normal Line
        line_x = mean + z_scores * std_overall

        # สเกลแกน Y แบบ Probability Paper
        tick_probs = [0.1, 1, 5, 10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 99, 99.9]
        tick_z = stats.norm.ppf(np.array(tick_probs) / 100.0)

        fig_prob = go.Figure()
        fig_prob.add_trace(go.Scatter(
            x=sorted_df[selected_col], y=z_scores, mode='markers', name='Data Points',
            marker=dict(size=9, color='lightgray', line=dict(width=1.5, color='black')),
            customdata=np.stack((sorted_df["Row_ID"], probs, sorted_df[group_col] if group_col != "ไม่แยกกลุ่ม" else ["-"]*n), axis=-1),
            hovertemplate="<b>⚠️ Row ที่: %{customdata[0]}</b> (Cavity: %{customdata[2]})<br>ค่าที่วัดได้: %{x:.5f}<br>Percent: %{customdata[1]:.2f}%<extra></extra>"
        ))
        fig_prob.add_trace(go.Scatter(x=line_x, y=z_scores, mode='lines', name='Normal Fit Line', line=dict(color='black', width=1.5)))

        fig_prob.update_layout(
            title=f"Normal Probability Plot of {selected_col} (เอาเมาส์ชี้ที่จุดเพื่อดูเลขบรรทัด)",
            xaxis_title="Measurement",
            yaxis=dict(title="Percent", tickmode='array', tickvals=tick_z, ticktext=[str(p) for p in tick_probs]),
            height=580
        )
        
        c1, c2 = st.columns([3, 1])
        with c1:
            st.plotly_chart(fig_prob, use_container_width=True)
        with c2:
            st.markdown("#### Normality Test")
            status = "✅ Normal (P ≥ 0.05)" if ad_pval >= 0.05 else "❌ Non-Normal (P < 0.05)"
            st.info(f"**สรุปผล:** {status}")
            st.metric("P-Value (Anderson-Darling)", f"{ad_pval:.4f}")
            st.metric("AD Statistic", f"{ad_stat:.3f}")
            st.metric("P-Value (Shapiro-Wilk)", f"{shapiro_pval:.4f}")
            st.caption("💡 **วิธีปรับค่า:** เอาเมาส์ชี้จุดที่กระโดดออกจากเส้นเพื่อดูเลข **Row ที่...** แล้วเลื่อนขึ้นไปแก้ตัวเลขในตารางด้านบน กราฟและค่า P-Value จะคำนวณใหม่ทันที")
