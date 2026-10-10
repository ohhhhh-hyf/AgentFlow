import os
import sys
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.enum.text import PP_ALIGN
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE

def hex_to_rgb(hex_str):
    hex_str = hex_str.lstrip('#')
    return RGBColor(*(int(hex_str[i:i+2], 16) for i in (0, 2, 4)))

# Color Palette definition
C_NAVY_DARK = hex_to_rgb('0B132B')      # Deep Navy Dark background
C_NAVY_CARD = hex_to_rgb('1C2541')      # Card on dark bg
C_BG_LIGHT  = hex_to_rgb('F8FAFC')      # Crisp slate light bg
C_CARD_BG   = hex_to_rgb('FFFFFF')      # White card
C_CARD_BORDER = hex_to_rgb('E2E8F0')    # Subtle border
C_PRIMARY   = hex_to_rgb('1E40AF')      # Classic deep blue
C_PRIMARY_LIGHT = hex_to_rgb('EFF6FF')  # Very light blue
C_ACCENT_CYAN = hex_to_rgb('0284C7')    # Sky / Cyan
C_ACCENT_TEAL = hex_to_rgb('0D9488')    # Teal
C_ACCENT_AMBER= hex_to_rgb('D97706')    # Amber
C_ACCENT_ROSE = hex_to_rgb('E11D48')    # Rose
C_TEXT_MAIN = hex_to_rgb('0F172A')      # Slate 900
C_TEXT_MUTED= hex_to_rgb('475569')      # Slate 600
C_TEXT_LIGHT= hex_to_rgb('94A3B8')      # Slate 400
C_WHITE     = hex_to_rgb('FFFFFF')

FONT_HEADING = "Microsoft YaHei"
FONT_BODY = "Microsoft YaHei"

def create_deck():
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank_layout = prs.slide_layouts[6]

    def set_slide_background(slide, color):
        bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, prs.slide_height)
        bg.fill.solid()
        bg.fill.fore_color.rgb = color
        bg.line.fill.background()
        return bg

    def add_header(slide, title, category="MEETING AGENT ARCHITECTURE", slide_num=None):
        # Category tag / pill
        cat_box = slide.shapes.add_textbox(Inches(0.8), Inches(0.4), Inches(8), Inches(0.35))
        tf_cat = cat_box.text_frame
        tf_cat.word_wrap = True
        tf_cat.margin_left = tf_cat.margin_right = tf_cat.margin_top = tf_cat.margin_bottom = 0
        p_cat = tf_cat.paragraphs[0]
        p_cat.text = category.upper()
        p_cat.font.name = FONT_HEADING
        p_cat.font.size = Pt(10)
        p_cat.font.bold = True
        p_cat.font.color.rgb = C_ACCENT_CYAN

        # Title
        title_box = slide.shapes.add_textbox(Inches(0.8), Inches(0.72), Inches(11), Inches(0.6))
        tf_title = title_box.text_frame
        tf_title.word_wrap = True
        tf_title.margin_left = tf_title.margin_right = tf_title.margin_top = tf_title.margin_bottom = 0
        p_title = tf_title.paragraphs[0]
        p_title.text = title
        p_title.font.name = FONT_HEADING
        p_title.font.size = Pt(22)
        p_title.font.bold = True
        p_title.font.color.rgb = C_TEXT_MAIN

        # Decorative line
        line = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.8), Inches(1.35), Inches(11.733), Inches(0.02))
        line.fill.solid()
        line.fill.fore_color.rgb = C_CARD_BORDER
        line.line.fill.background()

        if slide_num:
            num_box = slide.shapes.add_textbox(Inches(12.0), Inches(0.5), Inches(0.8), Inches(0.3))
            tf_num = num_box.text_frame
            p_num = tf_num.paragraphs[0]
            p_num.alignment = PP_ALIGN.RIGHT
            p_num.text = f"{slide_num:02d}"
            p_num.font.name = FONT_HEADING
            p_num.font.size = Pt(12)
            p_num.font.bold = True
            p_num.font.color.rgb = C_TEXT_LIGHT

    def add_card(slide, left, top, width, height, bg_color=C_CARD_BG, border_color=C_CARD_BORDER):
        card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height)
        card.fill.solid()
        card.fill.fore_color.rgb = bg_color
        if border_color:
            card.line.color.rgb = border_color
            card.line.width = Pt(1)
        else:
            card.line.fill.background()
        return card

    # =========================================================================
    # SLIDE 1: COVER
    # =========================================================================
    s1 = prs.slides.add_slide(blank_layout)
    set_slide_background(s1, C_NAVY_DARK)

    # Accent decorative background banner
    dec1 = s1.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(1.0), Inches(11.733), Inches(5.5))
    dec1.fill.solid()
    dec1.fill.fore_color.rgb = C_NAVY_CARD
    dec1.line.color.rgb = hex_to_rgb('334155')
    dec1.line.width = Pt(1.5)

    # Category Pill
    pill = s1.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(1.4), Inches(1.6), Inches(3.2), Inches(0.42))
    pill.fill.solid()
    pill.fill.fore_color.rgb = hex_to_rgb('1E293B')
    pill.line.color.rgb = C_ACCENT_CYAN
    pill.line.width = Pt(1)
    tf = pill.text_frame
    p = tf.paragraphs[0]
    p.text = "ENTERPRISE AI AGENT SYSTEM"
    p.alignment = PP_ALIGN.CENTER
    p.font.name = FONT_HEADING
    p.font.size = Pt(10)
    p.font.bold = True
    p.font.color.rgb = C_ACCENT_CYAN

    # Main Title
    tb = s1.shapes.add_textbox(Inches(1.4), Inches(2.2), Inches(10.5), Inches(1.8))
    tf = tb.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = "Meeting 领域 Agent 架构解构与演进"
    p.font.name = FONT_HEADING
    p.font.size = Pt(36)
    p.font.bold = True
    p.font.color.rgb = C_WHITE

    p2 = tf.add_paragraph()
    p2.text = "深度拆解：会议理解 · 子任务分工 · 审核校验 · 渲染展现 · 记忆体系与并发写"
    p2.font.name = FONT_BODY
    p2.font.size = Pt(18)
    p2.font.color.rgb = hex_to_rgb('94A3B8')

    # 3 Summary Cards at bottom of cover
    items = [
        ("四层闭环架构", "理解感知、任务执行、质量审核、多模态渲染的协同机制", C_ACCENT_CYAN),
        ("当前产业进展", "从单纯ASR总结跨越到全流程结构化辅助与落地痛点", C_ACCENT_TEAL),
        ("未来演进突破", "跨会议长期组织记忆 + 结构化模板并发写入引擎", C_ACCENT_AMBER)
    ]
    card_w = Inches(3.2)
    card_gap = Inches(0.4)
    start_x = Inches(1.4)
    for i, (title, desc, accent) in enumerate(items):
        cx = start_x + i * (card_w + card_gap)
        sc = s1.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, cx, Inches(4.3), card_w, Inches(1.6))
        sc.fill.solid()
        sc.fill.fore_color.rgb = hex_to_rgb('0F172A')
        sc.line.color.rgb = accent
        sc.line.width = Pt(1)
        stf = sc.text_frame
        stf.word_wrap = True
        stf.margin_top = Inches(0.2)
        stf.margin_left = Inches(0.2)
        stf.margin_right = Inches(0.2)
        
        sp1 = stf.paragraphs[0]
        sp1.text = title
        sp1.font.name = FONT_HEADING
        sp1.font.size = Pt(14)
        sp1.font.bold = True
        sp1.font.color.rgb = accent

        sp2 = stf.add_paragraph()
        sp2.text = desc
        sp2.font.name = FONT_BODY
        sp2.font.size = Pt(10.5)
        sp2.font.color.rgb = hex_to_rgb('CBD5E1')

    # =========================================================================
    # SLIDE 2: OVERALL ARCHITECTURE (全景逻辑分层)
    # =========================================================================
    s2 = prs.slides.add_slide(blank_layout)
    set_slide_background(s2, C_BG_LIGHT)
    add_header(s2, "Meeting 领域 Agent 总体分层架构全景图", "SYSTEM ARCHITECTURE OVERVIEW", 2)

    layers = [
        ("Layer 1: 感知与理解层", "Meeting Understanding Engine", 
         "多模态感知接入（ASR音频流、声纹分离、屏幕OCR、聊天记录）\n"
         "语义层级解析：语篇切分 (Segmentation)、议题识别、上下文对齐、意图与实体抽取\n"
         "输出：带有时间戳、发言人、议题索引的精细化多模态结构化会议图谱 (Meeting Context Graph)",
         C_PRIMARY, C_PRIMARY_LIGHT),

        ("Layer 2: 任务协同执行层", "Specialized Sub-task Agents Swarm",
         "纪要生成 Agent：议题级深度摘要、核心论点归纳、关键观点对比\n"
         "待办闭环 Agent：提取行动项(Action Items)、责任人指派、工期与验收条件\n"
         "决议追踪 Agent：锁定明确结论、表决共识、争议未决点与前置条件\n"
         "问答分析 Agent：实时跨发言人观点溯源、时间戳语义搜索、交互式问答",
         C_ACCENT_CYAN, hex_to_rgb('F0F9FF')),

        ("Layer 3: 质检与可信审核层", "Audit & Verification Engine",
         "事实一致性校验 (Fact-Checking)：反向溯源对齐原始转写，证据链强制引用\n"
         "幻觉与逻辑消解：消除前后矛盾论断、过滤模糊主语错位归因\n"
         "完整度与合规审查：对照议程校验遗漏事项，企业机密与合规敏感词脱敏",
         C_ACCENT_AMBER, hex_to_rgb('FFFBEB')),

        ("Layer 4: 渲染与交互展现层", "Multi-modal Rendering & Delivery",
         "多端自适应渲染：Markdown / Word / PDF / 在线协同文档 (飞书/Notion/钉钉)\n"
         "结构化可视化生成：Mermaid流程图、思维导图、甘特图、时间线图谱\n"
         "场景化微排版：IM即时通信群卡片 (30s电梯摘要)、待办一键认领卡片",
         C_ACCENT_TEAL, hex_to_rgb('F0FDFA'))
    ]

    layer_w = Inches(11.733)
    layer_h = Inches(1.22)
    start_y = Inches(1.6)
    gap_y = Inches(0.18)

    for i, (title_cn, title_en, desc, col_accent, col_bg) in enumerate(layers):
        ly = start_y + i * (layer_h + gap_y)
        card = add_card(s2, Inches(0.8), ly, layer_w, layer_h, col_bg, col_accent)
        
        # Left tag bar
        tag_bar = s2.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.8), ly, Inches(0.15), layer_h)
        tag_bar.fill.solid()
        tag_bar.fill.fore_color.rgb = col_accent
        tag_bar.line.fill.background()

        tb = s2.shapes.add_textbox(Inches(1.1), ly + Inches(0.12), Inches(3.8), layer_h - Inches(0.24))
        tf = tb.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_top = tf.margin_right = tf.margin_bottom = 0
        p1 = tf.paragraphs[0]
        p1.text = title_cn
        p1.font.name = FONT_HEADING
        p1.font.size = Pt(13)
        p1.font.bold = True
        p1.font.color.rgb = col_accent

        p2 = tf.add_paragraph()
        p2.text = title_en
        p2.font.name = FONT_BODY
        p2.font.size = Pt(9.5)
        p2.font.color.rgb = C_TEXT_MUTED

        # Right Content
        tb_r = s2.shapes.add_textbox(Inches(5.0), ly + Inches(0.12), Inches(7.3), layer_h - Inches(0.24))
        tf_r = tb_r.text_frame
        tf_r.word_wrap = True
        tf_r.margin_left = tf_r.margin_top = tf_r.margin_right = tf_r.margin_bottom = 0
        for line_idx, line in enumerate(desc.split('\n')):
            if line_idx == 0:
                p = tf_r.paragraphs[0]
            else:
                p = tf_r.add_paragraph()
            p.text = "• " + line
            p.font.name = FONT_BODY
            p.font.size = Pt(10)
            p.font.color.rgb = C_TEXT_MAIN

    # =========================================================================
    # SLIDE 3: MEETING UNDERSTANDING (会议理解层深入)
    # =========================================================================
    s3 = prs.slides.add_slide(blank_layout)
    set_slide_background(s3, C_BG_LIGHT)
    add_header(s3, "核心底座：meeting_understanding 理解引擎深入", "DEEP DIVE: UNDERSTANDING ENGINE", 3)

    cols_3 = [
        ("多模态数据摄入与清洗", "Multimodal Ingestion & Alignment", [
            ("ASR音文转录", "支持长音频分块、流式转写、低延迟声学重打标"),
            ("声纹说话人分离", "Speaker Diarization，解决同音/交叉插话难题"),
            ("屏幕OCR与视觉帧", "捕捉PPT换页、白板笔迹、代码演示关键帧"),
            ("会中交互日志", "聊天室留言、举手互动、实时投票问卷数据")
        ], C_PRIMARY),

        ("语篇结构化与议题切分", "Discourse & Topic Segmentation", [
            ("动态滑动窗口切分", "基于语义连贯度 (TextTiling) 与议程锚点分割"),
            ("议题聚类与对齐", "将散乱发言归并映射到预设/自发现的议程体系"),
            ("主线与插话辨识", "识别发散性寒暄、离题插曲并打上分支标签"),
            ("实体与意图挖掘", "识别责任人、时间、产品模块、同意/质疑态度")
        ], C_ACCENT_CYAN),

        ("长上下文图谱化建模", "Context Graph & Knowledge Pack", [
            ("层次化上下文封装", "宏观会议大纲 ➔ 议题微结构 ➔ 发言人发言对"),
            ("时序依存关系链", "构建发言的前后因果承接与逻辑因果网络"),
            ("多模态锚点绑定", "文字-时间戳-PPT幻灯片页码三元组绑定"),
            ("标准化上下文包", "向子Agent输出高保真、低噪声的结构化Prompt环境")
        ], C_ACCENT_TEAL)
    ]

    card_w = Inches(3.75)
    card_gap = Inches(0.24)
    start_x = Inches(0.8)

    for i, (title_cn, title_en, subitems, accent_col) in enumerate(cols_3):
        cx = start_x + i * (card_w + card_gap)
        card = add_card(s3, cx, Inches(1.6), card_w, Inches(5.3), C_CARD_BG, C_CARD_BORDER)
        
        # Header Box inside card
        hb = s3.shapes.add_shape(MSO_SHAPE.RECTANGLE, cx, Inches(1.6), card_w, Inches(0.85))
        hb.fill.solid()
        hb.fill.fore_color.rgb = accent_col
        hb.line.fill.background()
        
        h_tf = hb.text_frame
        h_tf.word_wrap = True
        h_tf.margin_left = Inches(0.2)
        h_p1 = h_tf.paragraphs[0]
        h_p1.text = title_cn
        h_p1.font.name = FONT_HEADING
        h_p1.font.size = Pt(13)
        h_p1.font.bold = True
        h_p1.font.color.rgb = C_WHITE

        h_p2 = h_tf.add_paragraph()
        h_p2.text = title_en
        h_p2.font.name = FONT_BODY
        h_p2.font.size = Pt(9)
        h_p2.font.color.rgb = hex_to_rgb('E2E8F0')

        # Items
        item_y = Inches(2.65)
        for (stitle, sdesc) in subitems:
            ic = add_card(s3, cx + Inches(0.15), item_y, card_w - Inches(0.3), Inches(0.95), hex_to_rgb('F8FAFC'), C_CARD_BORDER)
            itf = ic.text_frame
            itf.word_wrap = True
            itf.margin_top = Inches(0.1)
            itf.margin_left = Inches(0.12)
            itf.margin_right = Inches(0.12)
            
            ip1 = itf.paragraphs[0]
            ip1.text = stitle
            ip1.font.name = FONT_HEADING
            ip1.font.size = Pt(11)
            ip1.font.bold = True
            ip1.font.color.rgb = C_TEXT_MAIN

            ip2 = itf.add_paragraph()
            ip2.text = sdesc
            ip2.font.name = FONT_BODY
            ip2.font.size = Pt(9.5)
            ip2.font.color.rgb = C_TEXT_MUTED
            item_y += Inches(1.05)

    # =========================================================================
    # SLIDE 4: SUB-TASK AGENTS SWARM (子任务 Agent 集群)
    # =========================================================================
    s4 = prs.slides.add_slide(blank_layout)
    set_slide_background(s4, C_BG_LIGHT)
    add_header(s4, "分工协同：专业子任务 Agent 集群设计", "SPECIALIZED SUB-TASK AGENTS SWARM", 4)

    subagents = [
        ("纪要生成 Agent", "Meeting Minutes & Summary Agent",
         "• 核心定位：多层级精细化纪要提取\n"
         "• 分层产出：高管1页纸电梯摘要 + 议题展开深度纪要 + 发言人观点辨析\n"
         "• 特殊机制：去口语化重塑、观点与事实分离、重点论据提取保留",
         C_PRIMARY),

        ("待办闭环 Agent", "Action Items & Task Agent",
         "• 核心定位：可落地的明确任务(Action Items)提取\n"
         "• 关键字段：任务名称、主责人(Assignee)、协作者、截止时间(DDL)、验收指标\n"
         "• 系统联动：对接企业工单系统 (Jira, 飞书任务, TAPD) 自动生成草稿",
         C_ACCENT_CYAN),

        ("决议追踪 Agent", "Decisions & Consensus Agent",
         "• 核心定位：锁定重大会议产出与组织承诺\n"
         "• 维度拆解：最终确定决策、附带触发条件(If-Then)、表决赞否比例\n"
         "• 争议标记：明确列出“搁置争议、待下次会议评审”的未决事项",
         C_ACCENT_TEAL),

        ("问答检索 Agent", "Meeting Copilot / QA Agent",
         "• 核心定位：会后/会中交互式语义问答与情报挖掘\n"
         "• 交互能力：跨议题交叉验证、特定发言人立场查询（“张三为什么反对方案B？”）\n"
         "• 溯源保障：毫秒级秒出音视频对应时间戳与发言切片",
         C_ACCENT_AMBER),

        ("态势风控 Agent", "Risk & Sentiment Agent",
         "• 核心定位：识别项目潜在隐患与团队协同障碍\n"
         "• 态势感知：发言主导权分布、负面情绪/激烈冲突预警、跨部门摩擦点识别\n"
         "• 风险预测：排期乐观偏差识别、跨团队依赖断裂预警",
         C_ACCENT_ROSE),

        ("角色画像 Agent", "Speaker Profiling & Alignment",
         "• 核心定位：参会人职能定位与贡献度量化\n"
         "• 画像维度：发言权重、决策拍板频次、建设性建议提出率\n"
         "• 辅助纠偏：提示会议倾听不足或某角色发言缺失（如QA/架构师未发言）",
         hex_to_rgb('4F46E5'))
    ]

    card_w = Inches(3.75)
    card_h = Inches(2.55)
    start_x = Inches(0.8)
    gap_x = Inches(0.24)
    start_y = Inches(1.6)
    gap_y = Inches(0.25)

    for i, (title_cn, title_en, content, col) in enumerate(subagents):
        row = i // 3
        col_idx = i % 3
        cx = start_x + col_idx * (card_w + gap_x)
        cy = start_y + row * (card_h + gap_y)

        c = add_card(s4, cx, cy, card_w, card_h, C_CARD_BG, C_CARD_BORDER)
        
        # Color bar top
        bar = s4.shapes.add_shape(MSO_SHAPE.RECTANGLE, cx, cy, card_w, Inches(0.08))
        bar.fill.solid()
        bar.fill.fore_color.rgb = col
        bar.line.fill.background()

        tb = s4.shapes.add_textbox(cx + Inches(0.2), cy + Inches(0.18), card_w - Inches(0.4), card_h - Inches(0.3))
        tf = tb.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_top = tf.margin_right = tf.margin_bottom = 0

        p1 = tf.paragraphs[0]
        p1.text = title_cn
        p1.font.name = FONT_HEADING
        p1.font.size = Pt(13)
        p1.font.bold = True
        p1.font.color.rgb = col

        p2 = tf.add_paragraph()
        p2.text = title_en
        p2.font.name = FONT_BODY
        p2.font.size = Pt(8.5)
        p2.font.color.rgb = C_TEXT_LIGHT

        for line in content.split('\n'):
            p = tf.add_paragraph()
            p.text = line
            p.font.name = FONT_BODY
            p.font.size = Pt(9.5)
            p.font.color.rgb = C_TEXT_MAIN

    # =========================================================================
    # SLIDE 5: AUDIT & VERIFICATION AGENT (审核与可信机制)
    # =========================================================================
    s5 = prs.slides.add_slide(blank_layout)
    set_slide_background(s5, C_BG_LIGHT)
    add_header(s5, "防幻觉与质量把控：审核 Agent (Audit & Verification)", "RELIABILITY: AUDIT & FACT-CHECKING", 5)

    # 2 Big Cards: Left = 4 Core Verification Dimensions, Right = Closed-loop Reflection & Correction
    # Left Card
    left_w = Inches(6.8)
    card_l = add_card(s5, Inches(0.8), Inches(1.6), left_w, Inches(5.3), C_CARD_BG, C_CARD_BORDER)
    
    tb_l = s5.shapes.add_textbox(Inches(1.1), Inches(1.8), left_w - Inches(0.6), Inches(5.0))
    tf_l = tb_l.text_frame
    tf_l.word_wrap = True
    tf_l.margin_left = tf_l.margin_top = tf_l.margin_right = tf_l.margin_bottom = 0
    
    p = tf_l.paragraphs[0]
    p.text = "四维可信审核体系 (Four-Dimensional Audit Engine)"
    p.font.name = FONT_HEADING
    p.font.size = Pt(15)
    p.font.bold = True
    p.font.color.rgb = C_PRIMARY

    audit_dims = [
        ("1. 事实一致性与反向溯源 (Fact Grounding)", 
         "利用 NLI (自然语言推理) 模型进行逐句反向蕴含验证。生成的每一条纪要和待办必须与原始音视频转写建立双向对齐 (Bi-directional Attribution)。凡无证据链支持的论断直接标黄预警或自动剔除。"),
        ("2. 责任与时间主体消解 (Coreference & Ambiguity)", 
         "严查口语化代词“那个事你搞一下”、“下周五之前”引起的歧义。审核 Agent 核实“你”是否准确归因到对应发言人，“下周五”是否根据会议发生时间准确换算成绝对公历日期 (YYYY-MM-DD)。"),
        ("3. 逻辑冲突与表决矛盾 (Logical Contradiction)", 
         "排查“决议事项”与“行动项”之间的冲突。例如：决议放弃方案A，但待办中仍存在“调研方案A供应商”。一旦发现前后自相矛盾，触发一致性仲裁。"),
        ("4. 合规隐私与信息保密 (Compliance & Privacy Guard)", 
         "自动识别个人敏感隐私 (PII)、员工薪酬、未经公开的财务数据、客户核心机密，按企业安全策略执行自动脱敏或权限级展示隔离。")
    ]

    for (dname, ddesc) in audit_dims:
        p_t = tf_l.add_paragraph()
        p_t.text = dname
        p_t.font.name = FONT_HEADING
        p_t.font.size = Pt(11.5)
        p_t.font.bold = True
        p_t.font.color.rgb = C_ACCENT_AMBER

        p_d = tf_l.add_paragraph()
        p_d.text = ddesc
        p_d.font.name = FONT_BODY
        p_d.font.size = Pt(9.5)
        p_d.font.color.rgb = C_TEXT_MAIN

    # Right Card: The Reflection & Feedback Mechanism
    right_w = Inches(4.7)
    card_r = add_card(s5, Inches(7.833), Inches(1.6), right_w, Inches(5.3), hex_to_rgb('F8FAFC'), C_ACCENT_CYAN)

    tb_r = s5.shapes.add_textbox(Inches(8.1), Inches(1.8), right_w - Inches(0.5), Inches(5.0))
    tf_r = tb_r.text_frame
    tf_r.word_wrap = True
    tf_r.margin_left = tf_r.margin_top = tf_r.margin_right = tf_r.margin_bottom = 0

    p_rt = tf_r.paragraphs[0]
    p_rt.text = "闭环自省与重试反馈机制 (Self-Correction Loop)"
    p_rt.font.name = FONT_HEADING
    p_rt.font.size = Pt(14)
    p_rt.font.bold = True
    p_rt.font.color.rgb = C_TEXT_MAIN

    steps_audit = [
        ("Step 1: 生成初稿", "子任务 Agent 输出结构化 JSON 初稿及候选证据索引。"),
        ("Step 2: 独立核验", "审核 Agent 作为独立评估者运行，对候选稿件打标 (Confidence & Grounding Score)。"),
        ("Step 3: 违规诊断与差分反馈", "若置信度低于阈值 (如 < 0.85)，生成精确的 Diagnostic Feedback (例如：缺少时间戳证据、主语模糊)。"),
        ("Step 4: 靶向自适应修复", "子 Agent 仅针对被质疑的特定字段进行局部 Prompt 重试，无需全篇重写，大幅节约延时与Token。"),
        ("Step 5: 人机协同 (HITL)", "对于极高风险或低置信度内容，打上 [需人工复核] 标记并高亮原文供用户一键决策。")
    ]

    for (stitle, sbody) in steps_audit:
        ps_t = tf_r.add_paragraph()
        ps_t.text = stitle
        ps_t.font.name = FONT_HEADING
        ps_t.font.size = Pt(10.5)
        ps_t.font.bold = True
        ps_t.font.color.rgb = C_ACCENT_CYAN

        ps_b = tf_r.add_paragraph()
        ps_b.text = sbody
        ps_b.font.name = FONT_BODY
        ps_b.font.size = Pt(9)
        ps_b.font.color.rgb = C_TEXT_MUTED

    # =========================================================================
    # SLIDE 6: RENDERING & PRESENTATION AGENT (渲染与展现 Agent)
    # =========================================================================
    s6 = prs.slides.add_slide(blank_layout)
    set_slide_background(s6, C_BG_LIGHT)
    add_header(s6, "多模态与场景适配：渲染 Agent (Rendering Engine)", "MULTI-MODAL RENDERING & DELIVERY", 6)

    render_modes = [
        ("场景一：IM即时通讯交互卡片", "Enterprise IM Interactive Cards",
         "• 核心形态：飞书/钉钉/企微消息流卡片\n"
         "• 内容结构：30秒高管极简速览 + 核心待办认领按钮\n"
         "• 交互特性：支持在群聊中一键勾选‘认领任务’、点击查看录音原文引用片段",
         C_PRIMARY),

        ("场景二：协同知识库在线文档", "Rich Online Docs (Notion / Feishu)",
         "• 核心形态：模块化、块级结构化在线文档\n"
         "• 视觉排版：议程折叠展开、Callout高亮警示框、责任人@提及、任务看板视图\n"
         "• 动态联动：与团队知识库自动关联，自动创建跨会议专题合辑",
         C_ACCENT_CYAN),

        ("场景三：结构化图表与多模态可视化", "Diagrams & Mindmaps (Mermaid / SVG)",
         "• 思维导图：议题树状展开，全景结构一目了然\n"
         "• 流程与甘特图：待办事项交付里程碑甘特图，前后置依赖有向图\n"
         "• 发言拓扑图：各参会人发言频次与互动关系雷达图",
         C_ACCENT_TEAL),

        ("场景四：严谨商务汇报格式交付", "Formal Formats (Word / PDF / PPT)",
         "• 核心形态：遵循企业标准化模板规范的正式公文\n"
         "• 排版引擎：自动匹配企业页眉页脚、统一排版间距、图文混排分页保护\n"
         "• 归档审计：附带防篡改数字签名与音视频时间戳附录",
         C_ACCENT_AMBER)
    ]

    card_w = Inches(5.6)
    card_h = Inches(2.45)
    start_x = Inches(0.8)
    gap_x = Inches(0.533)
    start_y = Inches(1.6)
    gap_y = Inches(0.35)

    for i, (rtitle, rsub, rcontent, rcol) in enumerate(render_modes):
        row = i // 2
        col_idx = i % 2
        cx = start_x + col_idx * (card_w + gap_x)
        cy = start_y + row * (card_h + gap_y)

        c = add_card(s6, cx, cy, card_w, card_h, C_CARD_BG, C_CARD_BORDER)
        
        # Left tag stripe
        ts = s6.shapes.add_shape(MSO_SHAPE.RECTANGLE, cx, cy, Inches(0.12), card_h)
        ts.fill.solid()
        ts.fill.fore_color.rgb = rcol
        ts.line.fill.background()

        tb = s6.shapes.add_textbox(cx + Inches(0.3), cy + Inches(0.15), card_w - Inches(0.45), card_h - Inches(0.3))
        tf = tb.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_top = tf.margin_right = tf.margin_bottom = 0

        p1 = tf.paragraphs[0]
        p1.text = rtitle
        p1.font.name = FONT_HEADING
        p1.font.size = Pt(13)
        p1.font.bold = True
        p1.font.color.rgb = rcol

        p2 = tf.add_paragraph()
        p2.text = rsub
        p2.font.name = FONT_BODY
        p2.font.size = Pt(9)
        p2.font.color.rgb = C_TEXT_LIGHT

        for line in rcontent.split('\n'):
            p = tf.add_paragraph()
            p.text = line
            p.font.name = FONT_BODY
            p.font.size = Pt(10)
            p.font.color.rgb = C_TEXT_MAIN

    # =========================================================================
    # SLIDE 7: END-TO-END SYSTEM LOGIC FLOW (全流程执行逻辑图)
    # =========================================================================
    s7 = prs.slides.add_slide(blank_layout)
    set_slide_background(s7, C_BG_LIGHT)
    add_header(s7, "会议 Agent 全流程端到端执行逻辑流", "END-TO-END EXECUTION LOGIC FLOW", 7)

    # 5 Sequential Pipeline Stages represented horizontally
    stages = [
        ("阶段一", "多模态摄入与对齐", "Multimodal Ingest", 
         "• 音频ASR长流识别\n• 声纹分离定界\n• 屏幕共享OCR提取\n• 生成时序转写对齐流", C_PRIMARY),
        ("阶段二", "会议理解中枢", "meeting_understanding", 
         "• 议题自适应切分\n• 主题聚类与离题过滤\n• 实体意图图谱化\n• 构建上下文索引表", C_ACCENT_CYAN),
        ("阶段三", "子任务并发派发", "Sub-task Swarm", 
         "• 纪要Agent：深度提炼\n• 待办Agent：责任人闭环\n• 决议Agent：明确共识\n• 问答Agent：知识向量化", C_ACCENT_TEAL),
        ("阶段四", "严格审核仲裁", "Audit & Consistency", 
         "• 事实溯源与反向蕴含\n• 口语代词消解纠偏\n• 前后矛盾冲突仲裁\n• 违规诊断与自省重试", C_ACCENT_AMBER),
        ("阶段五", "渲染与多端交付", "Rendering & Delivery", 
         "• 动态槽位拼装合稿\n• 多端UI自适应排版\n• Mermaid思维导图生成\n• 推送IM/文档/任务系统", C_ACCENT_ROSE)
    ]

    pipe_w = Inches(2.15)
    pipe_gap = Inches(0.24)
    start_x = Inches(0.8)
    pipe_y = Inches(1.6)
    pipe_h = Inches(4.3)

    for i, (s_idx, s_title, s_en, s_bullets, s_col) in enumerate(stages):
        cx = start_x + i * (pipe_w + pipe_gap)
        c = add_card(s7, cx, pipe_y, pipe_w, pipe_h, C_CARD_BG, C_CARD_BORDER)

        # Stage Header
        sh = s7.shapes.add_shape(MSO_SHAPE.RECTANGLE, cx, pipe_y, pipe_w, Inches(0.75))
        sh.fill.solid()
        sh.fill.fore_color.rgb = s_col
        sh.line.fill.background()

        s_tf = sh.text_frame
        s_tf.word_wrap = True
        s_tf.margin_left = Inches(0.12)
        sp1 = s_tf.paragraphs[0]
        sp1.text = f"{s_idx}: {s_title}"
        sp1.font.name = FONT_HEADING
        sp1.font.size = Pt(11)
        sp1.font.bold = True
        sp1.font.color.rgb = C_WHITE

        sp2 = s_tf.add_paragraph()
        sp2.text = s_en
        sp2.font.name = FONT_BODY
        sp2.font.size = Pt(8)
        sp2.font.color.rgb = hex_to_rgb('E2E8F0')

        # Content
        tb = s7.shapes.add_textbox(cx + Inches(0.12), pipe_y + Inches(0.85), pipe_w - Inches(0.24), pipe_h - Inches(0.95))
        tf = tb.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_top = tf.margin_right = tf.margin_bottom = 0

        for b_line in s_bullets.split('\n'):
            p = tf.add_paragraph()
            p.text = b_line
            p.font.name = FONT_BODY
            p.font.size = Pt(9.5)
            p.font.color.rgb = C_TEXT_MAIN

        # Arrow indicator between stages
        if i < len(stages) - 1:
            arr_x = cx + pipe_w + Inches(0.04)
            arr_tb = s7.shapes.add_textbox(arr_x, pipe_y + Inches(2.0), Inches(0.18), Inches(0.3))
            atf = arr_tb.text_frame
            atf.margin_left = atf.margin_right = atf.margin_top = atf.margin_bottom = 0
            ap = atf.paragraphs[0]
            ap.text = "➔"
            ap.font.name = FONT_HEADING
            ap.font.size = Pt(14)
            ap.font.bold = True
            ap.font.color.rgb = C_TEXT_LIGHT

    # Bottom summary callout
    bot_card = add_card(s7, Inches(0.8), Inches(6.1), Inches(11.733), Inches(0.8), hex_to_rgb('EFF6FF'), C_PRIMARY)
    bot_tf = bot_card.text_frame
    bot_tf.word_wrap = True
    bot_tf.margin_left = Inches(0.3)
    bot_p = bot_tf.paragraphs[0]
    bot_p.text = "架构闭环关键原则：上游结构化解耦 ➔ 中游多Agent并行加速 ➔ 下游强制事实归因反思 ➔ 终端多模态无缝投递"
    bot_p.font.name = FONT_HEADING
    bot_p.font.size = Pt(11.5)
    bot_p.font.bold = True
    bot_p.font.color.rgb = C_PRIMARY

    # =========================================================================
    # SLIDE 8: CURRENT INDUSTRY PROGRESS & PAIN POINTS (当前进展与痛点)
    # =========================================================================
    s8 = prs.slides.add_slide(blank_layout)
    set_slide_background(s8, C_BG_LIGHT)
    add_header(s8, "产业现状盘点：当前进展与生产落地痛点", "CURRENT PROGRESS & REAL-WORLD BOTTLENECKS", 8)

    half_w = Inches(5.6)
    
    # Left: Current Achievements
    card_l = add_card(s8, Inches(0.8), Inches(1.6), half_w, Inches(5.3), C_CARD_BG, C_CARD_BORDER)
    # Header bar
    hbar_l = s8.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.8), Inches(1.6), half_w, Inches(0.65))
    hbar_l.fill.solid()
    hbar_l.fill.fore_color.rgb = C_ACCENT_TEAL
    hbar_l.line.fill.background()
    tf_hl = hbar_l.text_frame
    p_hl = tf_hl.paragraphs[0]
    p_hl.text = "当前已取得的重大技术突破 (What Works Today)"
    p_hl.font.name = FONT_HEADING
    p_hl.font.size = Pt(13)
    p_hl.font.bold = True
    p_hl.font.color.rgb = C_WHITE

    achievements = [
        ("长文本基座大模型红利普及", "百万上下文 (1M-2M Token) 使得2-4小时超长会议全文一次性喂入成为可能，召回率相较传统分块大幅提升。"),
        ("标品纪要成为主流协作工具标配", "飞书妙记、钉钉AI听伴、腾讯会议AI小助、Zoom AI Companion、Teams Copilot 全面普及，单场摘要成熟。"),
        ("ASR与声纹分离准确率跨越", "端到端语音大模型对专业术语、口音、中英混杂识别率突破95%，说话人识别稳定性大幅增强。"),
        ("流水线Agent初步落地", "从早期单一Prompt直接输出全文，进化到‘切分-摘要-待办抽取’的多步骤Pipeline或初步Subagents协同。")
    ]
    tb_ac = s8.shapes.add_textbox(Inches(1.1), Inches(2.4), half_w - Inches(0.6), Inches(4.3))
    tf_ac = tb_ac.text_frame
    tf_ac.word_wrap = True
    tf_ac.margin_left = tf_ac.margin_top = tf_ac.margin_right = tf_ac.margin_bottom = 0
    for idx, (atitle, adesc) in enumerate(achievements):
        if idx > 0:
            p_t = tf_ac.add_paragraph()
        else:
            p_t = tf_ac.paragraphs[0]
        p_t.text = f"✔ {atitle}"
        p_t.font.name = FONT_HEADING
        p_t.font.size = Pt(11)
        p_t.font.bold = True
        p_t.font.color.rgb = C_ACCENT_TEAL

        p_d = tf_ac.add_paragraph()
        p_d.text = adesc
        p_d.font.name = FONT_BODY
        p_d.font.size = Pt(9.5)
        p_d.font.color.rgb = C_TEXT_MAIN

    # Right: Pain points
    card_r = add_card(s8, Inches(6.933), Inches(1.6), half_w, Inches(5.3), C_CARD_BG, C_CARD_BORDER)
    hbar_r = s8.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(6.933), Inches(1.6), half_w, Inches(0.65))
    hbar_r.fill.solid()
    hbar_r.fill.fore_color.rgb = C_ACCENT_AMBER
    hbar_r.line.fill.background()
    tf_hr = hbar_r.text_frame
    p_hr = tf_hr.paragraphs[0]
    p_hr.text = "深水区核心瓶颈与落地痛点 (Critical Pain Points)"
    p_hr.font.name = FONT_HEADING
    p_hr.font.size = Pt(13)
    p_hr.font.bold = True
    p_hr.font.color.rgb = C_WHITE

    painpoints = [
        ("口语碎片化导致的‘事实张冠李戴’", "口语省略主语、频繁打断修正，导致模型经常将A提出的待办误扣在B头上，在商务/研发场景易引发协作事故。"),
        ("跨会议孤岛与上下文严重断裂", "每次会议被孤立处理，无法回答‘上周例会决议落实得如何’、‘该项目三个月来技术方案经历了哪些演变’。"),
        ("大文档端到端串行生成延时巨大", "复杂长会议生成详尽纪要耗时常常长达1-3分钟，用户体验断层，缺乏并发分块写入与流式组装机制。"),
        ("缺乏不可推卸的闭环证据链", "大多数产品输出为黑盒文本，缺乏与原始音频毫秒级精确反向锚定，导致专业法务、医疗、投资场景不敢直接采用。")
    ]
    tb_pp = s8.shapes.add_textbox(Inches(7.233), Inches(2.4), half_w - Inches(0.6), Inches(4.3))
    tf_pp = tb_pp.text_frame
    tf_pp.word_wrap = True
    tf_pp.margin_left = tf_pp.margin_top = tf_pp.margin_right = tf_pp.margin_bottom = 0
    for idx, (ptitle, pdesc) in enumerate(painpoints):
        if idx > 0:
            p_t = tf_pp.add_paragraph()
        else:
            p_t = tf_pp.paragraphs[0]
        p_t.text = f"✘ {ptitle}"
        p_t.font.name = FONT_HEADING
        p_t.font.size = Pt(11)
        p_t.font.bold = True
        p_t.font.color.rgb = C_ACCENT_AMBER

        p_d = tf_pp.add_paragraph()
        p_d.text = pdesc
        p_d.font.name = FONT_BODY
        p_d.font.size = Pt(9.5)
        p_d.font.color.rgb = C_TEXT_MAIN

    # =========================================================================
    # SLIDE 9: FUTURE EVOLUTION 1: LONG-TERM MEETING MEMORY (跨会议记忆体系)
    # =========================================================================
    s9 = prs.slides.add_slide(blank_layout)
    set_slide_background(s9, C_BG_LIGHT)
    add_header(s9, "未来演进一：构建企业级跨会议长期记忆网络", "FUTURE EVOLUTION: LONG-TERM MEMORY ARCHITECTURE", 9)

    mem_tiers = [
        ("工作记忆 (Working Memory)", "单场会议实时微上下文", 
         "• 范围：当前进行中会议的滑动音频窗口与实时对话状态\n"
         "• 机制：保留最近发言的短程注意力，维护当前议题的活动槽位\n"
         "• 核心作用：支持低延迟会中提问、实时字幕打标纠错", C_PRIMARY),

        ("情节记忆 (Episodic Memory)", "单场会议全景事件快照", 
         "• 范围：单场会议定稿后的结构化图谱、决议列表、音视频锚点\n"
         "• 机制：以事件(Event)为最小单元，固化参与者、时间戳、争论焦点\n"
         "• 核心作用：单场会议精确回溯、审计查询与反事实验证", C_ACCENT_CYAN),

        ("语义与组织记忆 (Semantic Memory)", "跨会议演进知识图谱", 
         "• 范围：多场次、多部门、跨季度的长期项目与组织知识演化网络\n"
         "• 机制：提取实体、项目、架构决策构建 Temporal Knowledge Graph\n"
         "• 核心作用：跨会议追踪决策变迁、跟进跨月度待办闭环完成度", C_ACCENT_TEAL),

        ("用户画像与偏好记忆 (User Profiling)", "角色化关注点自适应", 
         "• 范围：参会者的职能习惯、关注侧重与表达特征\n"
         "• 机制：高管偏好战略决策与ROI；技术TL偏好系统瓶颈与风险阻塞\n"
         "• 核心作用：‘千人千面’的个性化纪要推送与关键通知唤醒", C_ACCENT_AMBER)
    ]

    card_w = Inches(2.78)
    card_gap = Inches(0.2)
    start_x = Inches(0.8)
    for i, (mtitle, msub, mdesc, mcol) in enumerate(mem_tiers):
        cx = start_x + i * (card_w + card_gap)
        c = add_card(s9, cx, Inches(1.6), card_w, Inches(3.6), C_CARD_BG, C_CARD_BORDER)
        
        # Header strip
        hs = s9.shapes.add_shape(MSO_SHAPE.RECTANGLE, cx, Inches(1.6), card_w, Inches(0.8))
        hs.fill.solid()
        hs.fill.fore_color.rgb = mcol
        hs.line.fill.background()
        
        tf_h = hs.text_frame
        tf_h.word_wrap = True
        tf_h.margin_left = Inches(0.12)
        p1 = tf_h.paragraphs[0]
        p1.text = mtitle
        p1.font.name = FONT_HEADING
        p1.font.size = Pt(11)
        p1.font.bold = True
        p1.font.color.rgb = C_WHITE

        p2 = tf_h.add_paragraph()
        p2.text = msub
        p2.font.name = FONT_BODY
        p2.font.size = Pt(8.5)
        p2.font.color.rgb = hex_to_rgb('E2E8F0')

        tb = s9.shapes.add_textbox(cx + Inches(0.12), Inches(2.5), card_w - Inches(0.24), Inches(2.6))
        tf = tb.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_top = tf.margin_right = tf.margin_bottom = 0
        for line in mdesc.split('\n'):
            p = tf.add_paragraph()
            p.text = line
            p.font.name = FONT_BODY
            p.font.size = Pt(9.5)
            p.font.color.rgb = C_TEXT_MAIN

    # Bottom Architecture Highlight Box
    mem_flow = add_card(s9, Inches(0.8), Inches(5.4), Inches(11.733), Inches(1.5), hex_to_rgb('F0FDF4'), C_ACCENT_TEAL)
    tb_mf = mem_flow.text_frame
    tb_mf.word_wrap = True
    tb_mf.margin_left = Inches(0.3)
    tb_mf.margin_top = Inches(0.15)
    
    p = tb_mf.paragraphs[0]
    p.text = "跨会议决议生命周期闭环追踪机制 (Resolution Lifecycle Tracing)"
    p.font.name = FONT_HEADING
    p.font.size = Pt(12)
    p.font.bold = True
    p.font.color.rgb = C_ACCENT_TEAL

    p2 = tb_mf.add_paragraph()
    p2.text = "在召开本次会议时，记忆 Agent 自动检索关联项目上周/上月的未决议题与待办清单 ➔ 作为隐式上下文注入 meeting_understanding ➔ 在本次会议发言中主动对齐‘是否落实’ ➔ 形成跨会议闭环状态流：[提出] ➔ [推进中] ➔ [阻塞预警] ➔ [正式验收闭环]。彻底打破单次会议孤岛。"
    p2.font.name = FONT_BODY
    p2.font.size = Pt(10)
    p2.font.color.rgb = C_TEXT_MAIN

    # =========================================================================
    # SLIDE 10: FUTURE EVOLUTION 2: TEMPLATE CONCURRENT WRITING (模板并发写)
    # =========================================================================
    s10 = prs.slides.add_slide(blank_layout)
    set_slide_background(s10, C_BG_LIGHT)
    add_header(s10, "未来演进二：模板并发写与结构化组装引擎", "FUTURE EVOLUTION: CONCURRENT TEMPLATE WRITING", 10)

    # Left: Paradigm Comparison (Serial vs Concurrent)
    comp_w = Inches(5.6)
    card_comp = add_card(s10, Inches(0.8), Inches(1.6), comp_w, Inches(5.3), C_CARD_BG, C_CARD_BORDER)
    
    tb_cp = s10.shapes.add_textbox(Inches(1.1), Inches(1.8), comp_w - Inches(0.6), Inches(4.9))
    tf_cp = tb_cp.text_frame
    tf_cp.word_wrap = True
    tf_cp.margin_left = tf_cp.margin_top = tf_cp.margin_right = tf_cp.margin_bottom = 0

    p = tf_cp.paragraphs[0]
    p.text = "范式转变：传统串行流水 vs. 模板并发写"
    p.font.name = FONT_HEADING
    p.font.size = Pt(14)
    p.font.bold = True
    p.font.color.rgb = C_PRIMARY

    p_c1 = tf_cp.add_paragraph()
    p_c1.text = "传统单体串行生成 (Serial Generation - 痛点)："
    p_c1.font.name = FONT_HEADING
    p_c1.font.size = Pt(11)
    p_c1.font.bold = True
    p_c1.font.color.rgb = C_ACCENT_ROSE

    p_c1_d = tf_cp.add_paragraph()
    p_c1_d.text = "• 端到端单一大Prompt直接生成数千字长纪要\n• 耗时长 (60s-180s)，用户处于漫长白屏等待\n• 上下文注意力衰减，后半段待办与决议频繁遗漏\n• 无法根据企业各业务部门差异化模板自适应拼装"
    p_c1_d.font.name = FONT_BODY
    p_c1_d.font.size = Pt(9.5)
    p_c1_d.font.color.rgb = C_TEXT_MUTED

    p_c2 = tf_cp.add_paragraph()
    p_c2.text = "模板并发写架构 (Concurrent Slot Writing - 突破)："
    p_c2.font.name = FONT_HEADING
    p_c2.font.size = Pt(11)
    p_c2.font.bold = True
    p_c2.font.color.rgb = C_ACCENT_TEAL

    p_c2_d = tf_cp.add_paragraph()
    p_c2_d.text = "• 模板抽象语法树 (Template AST) 解构为离散槽位 (Slots)\n• DAG调度器根据依赖关系并发唤醒专属Subagent并行写入\n• 生成时延降低 70% (缩短至 15s 以内)\n• 每个槽位只消费专属高纯度上下文，细节提取度逼近100%"
    p_c2_d.font.name = FONT_BODY
    p_c2_d.font.size = Pt(9.5)
    p_c2_d.font.color.rgb = C_TEXT_MUTED

    # Right: The 4 Key Technical Mechanisms of Concurrent Writing
    mech_w = Inches(5.8)
    card_mech = add_card(s10, Inches(6.733), Inches(1.6), mech_w, Inches(5.3), hex_to_rgb('F8FAFC'), C_ACCENT_CYAN)

    tb_mc = s10.shapes.add_textbox(Inches(7.0), Inches(1.8), mech_w - Inches(0.5), Inches(4.9))
    tf_mc = tb_mc.text_frame
    tf_mc.word_wrap = True
    tf_mc.margin_left = tf_mc.margin_top = tf_mc.margin_right = tf_mc.margin_bottom = 0

    p_mct = tf_mc.paragraphs[0]
    p_mct.text = "模板并发写四大关键核心技术支撑"
    p_mct.font.name = FONT_HEADING
    p_mct.font.size = Pt(14)
    p_mct.font.bold = True
    p_mct.font.color.rgb = C_ACCENT_CYAN

    mechanisms = [
        ("1. Schema-driven Slot Definition (模板槽位化)", 
         "企业模板编译为JSON Schema或AST语法树，定义独立槽位：[高管摘要]、[议题1研讨]、[议题2技术评审]、[待办汇总矩阵]、[风险预警清单]。"),
        ("2. DAG 并发调度与上下文精确切片 (Slot Workers)", 
         "调度中心为每个槽位分配轻量级专职 Worker。Worker 仅拉取与自身槽位相关的精简上下文片段，多个Worker在云端毫秒级并发流式调用。"),
        ("3. 跨槽位一致性仲裁器 (Cross-Slot Consistency Resolver)", 
         "解决并发写冲突：议题一产生的待办与待办汇总表的一致性校验；全局发言人命名与缩写统一；全局决议编号规范化。"),
        ("4. 动态流式拼接与断点补偿 (Stream Assembler)", 
         "前端先就绪的槽位即时流式呈现，给用户带来零感知等待体验；个别槽位失败时仅针对该槽位重试补偿，无需全局推倒重来。")
    ]

    for (mname, mdesc) in mechanisms:
        pm_t = tf_mc.add_paragraph()
        pm_t.text = mname
        pm_t.font.name = FONT_HEADING
        pm_t.font.size = Pt(10.5)
        pm_t.font.bold = True
        pm_t.font.color.rgb = C_TEXT_MAIN

        pm_d = tf_mc.add_paragraph()
        pm_d.text = mdesc
        pm_d.font.name = FONT_BODY
        pm_d.font.size = Pt(9)
        pm_d.font.color.rgb = C_TEXT_MUTED

    # =========================================================================
    # SLIDE 11: TECHNICAL ROADMAP & SUMMARY (总结与技术落地路线图)
    # =========================================================================
    s11 = prs.slides.add_slide(blank_layout)
    set_slide_background(s11, C_BG_LIGHT)
    add_header(s11, "落地路线图：Meeting Agent 演进实施建议", "SUMMARY & TECHNICAL ROADMAP", 11)

    phases = [
        ("Phase 1: 夯实基石 (1-3月)", "结构化理解与单会闭环", [
            "上线 meeting_understanding 议题与实体切分引擎",
            "建设纪要、待办、决议三大多智能体并发流水线",
            "引入双向事实 Grounding 审核机制，杜绝幻觉"
        ], C_PRIMARY),

        ("Phase 2: 体验跃升 (3-6月)", "模板并发写与多模态渲染", [
            "落地基于 Schema 的模板槽位化并发写 (降延时70%)",
            "支持企微/飞书交互卡片与 Mermaid 架构图脑图输出",
            "打通企业 Jira / 飞书任务工单自动流转闭环"
        ], C_ACCENT_CYAN),

        ("Phase 3: 组织赋能 (6-12月)", "企业长期记忆网络构建", [
            "上线跨会议 Temporal Knowledge Graph 时序图谱",
            "实现跨场次重大决议全生命周期状态机追踪",
            "建立千人千面个性化角色画像与订阅式摘要触达"
        ], C_ACCENT_TEAL),

        ("Phase 4: 前沿探索 (12月+)", "会中自主协同与多模态原生", [
            "探索端到端原生音频 (Native Audio) 副语言情绪理解",
            "会中自主智能主持人：超时提醒、议程偏移插话纠偏",
            "与企业商业决策大脑打通，形成全自主执行闭环"
        ], C_ACCENT_AMBER)
    ]

    card_w = Inches(2.78)
    card_gap = Inches(0.2)
    start_x = Inches(0.8)

    for i, (p_title, p_sub, p_items, p_col) in enumerate(phases):
        cx = start_x + i * (card_w + card_gap)
        c = add_card(s11, cx, Inches(1.6), card_w, Inches(5.3), C_CARD_BG, C_CARD_BORDER)

        # Header Bar
        hb = s11.shapes.add_shape(MSO_SHAPE.RECTANGLE, cx, Inches(1.6), card_w, Inches(0.9))
        hb.fill.solid()
        hb.fill.fore_color.rgb = p_col
        hb.line.fill.background()

        h_tf = hb.text_frame
        h_tf.word_wrap = True
        h_tf.margin_left = Inches(0.12)
        hp1 = h_tf.paragraphs[0]
        hp1.text = p_title
        hp1.font.name = FONT_HEADING
        hp1.font.size = Pt(11)
        hp1.font.bold = True
        hp1.font.color.rgb = C_WHITE

        hp2 = h_tf.add_paragraph()
        hp2.text = p_sub
        hp2.font.name = FONT_BODY
        hp2.font.size = Pt(8.5)
        hp2.font.color.rgb = hex_to_rgb('E2E8F0')

        # Items inside card
        tb = s11.shapes.add_textbox(cx + Inches(0.15), Inches(2.65), card_w - Inches(0.3), Inches(4.1))
        tf = tb.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_top = tf.margin_right = tf.margin_bottom = 0

        for item in p_items:
            p = tf.add_paragraph()
            p.text = "• " + item
            p.font.name = FONT_BODY
            p.font.size = Pt(10)
            p.font.color.rgb = C_TEXT_MAIN
            
            # small spacer
            p_sp = tf.add_paragraph()
            p_sp.text = ""
            p_sp.font.size = Pt(6)

    # Save Presentation
    output_path = os.path.join(os.getcwd(), "Meeting_Agent_Architecture.pptx")
    prs.save(output_path)
    print(f"Successfully generated PowerPoint at: {output_path}")

if __name__ == "__main__":
    create_deck()
