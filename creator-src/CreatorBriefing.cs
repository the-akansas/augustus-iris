// Recovered from installed r127 assembly with ILSpy 8.2; no game rules changed.
using System;
using System.IO;
using System.Text;
using System.Drawing;
using System.Drawing.Imaging;
using System.Collections.Generic;
using System.Windows.Forms;
partial class ScenarioCreator {
 private TextBox briefingText;
	private void BuildBriefingTab()
	{
		TabPage tabPage = new TabPage("8  시나리오 브리핑");
		tabPage.BackColor = Paper;
		TabPage tabPage2 = tabPage;
		tabs.TabPages.Add(tabPage2);
		CreatorBriefingPanel creatorBriefingPanel = new CreatorBriefingPanel();
		briefingText = creatorBriefingPanel.Editor;
		briefingText.TextChanged += delegate
		{
			if (!loading && project != null)
			{
				project.briefing = briefingText.Text;
				Changed();
			}
		};
		tabPage2.Controls.Add(creatorBriefingPanel);
		startMessagePanel = creatorBriefingPanel;
		creatorBriefingPanel.StartTarget.DropDown += delegate { RefreshStartTargets(); };
		creatorBriefingPanel.StartTarget.SelectedIndexChanged += delegate { ShowStartMessage(); };
		creatorBriefingPanel.StartEditor.TextChanged += delegate
		{
			if (loading || startMessageLoading || project == null) return;
			var target = creatorBriefingPanel.StartTarget.SelectedItem as StartTarget;
			string text = creatorBriefingPanel.StartEditor.Text;
			if (project.start_message == null) project.start_message = new StartMessage();
			if (target == null || target.slot == null) project.start_message.common = text;
			else
			{
				if (project.start_message.per_city == null) project.start_message.per_city = new Dictionary<string, string>();
				if (string.IsNullOrWhiteSpace(text)) project.start_message.per_city.Remove(target.slot); else project.start_message.per_city[target.slot] = text;
			}
			Changed();
		};
	}
	private CreatorBriefingPanel startMessagePanel;
	private bool startMessageLoading;
	private class StartTarget { public string slot, label; public override string ToString() { return label; } }
	// "모든 플레이어" first, then one entry per player city. A city that has its own text is marked.
	private void RefreshStartTargets()
	{
		if (startMessagePanel == null || project == null) return;
		var box = startMessagePanel.StartTarget; var current = box.SelectedItem as StartTarget; string keep = current == null ? null : current.slot;
		startMessageLoading = true;
		box.Items.Clear(); box.Items.Add(new StartTarget { slot = null, label = "모든 플레이어 (공통 글)" });
		for (int i = 0; i < project.slots.Length; i++)
		{
			var s = project.slots[i]; bool own = project.start_message != null && project.start_message.per_city != null && project.start_message.per_city.ContainsKey(s.id);
			box.Items.Add(new StartTarget { slot = s.id, label = "P" + (i + 1) + " " + CityName(s.name_id) + (own ? " (글 있음)" : "") });
		}
		int index = 0; for (int i = 1; i < box.Items.Count; i++) if (((StartTarget)box.Items[i]).slot == keep) index = i;
		box.SelectedIndex = index;
		startMessageLoading = false;
	}
	private void ShowStartMessage()
	{
		if (startMessagePanel == null || project == null || startMessageLoading) return;
		var target = startMessagePanel.StartTarget.SelectedItem as StartTarget; string text = "";
		if (project.start_message != null)
		{
			if (target == null || target.slot == null) text = project.start_message.common ?? "";
			else if (project.start_message.per_city != null) project.start_message.per_city.TryGetValue(target.slot, out text);
		}
		startMessageLoading = true;
		startMessagePanel.StartEditor.Text = (text ?? "").Replace("\r\n", "\n").Replace("\n", "\r\n");
		startMessagePanel.StartHint.Text = target == null || target.slot == null ? "공통 글은 모든 플레이어에게 보입니다." : "이 도시의 플레이어에게만, 공통 글 아래에 이어서 보입니다. 비워 두면 공통 글만 보입니다.";
		startMessageLoading = false;
	}
	private void LoadStartMessage()
	{
		if (startMessagePanel == null) return;
		startMessagePanel.StartTarget.SelectedIndex = -1;
		RefreshStartTargets(); ShowStartMessage();
	}

	private static int BriefingProbe()
	{
		Scenario scenario = new Scenario();
		scenario.schema = 4;
		scenario.id = "briefing-check";
		scenario.title = "브리핑 검증";
		scenario.revision = 1;
		scenario.briefing = "두 도시의 협력\n함께 성장하세요. 한글과 줄바꿈 보존";
		scenario.rules = new Dictionary<string, object>();
		scenario.slots = new Slot[0];
		scenario.empire = new Empire
		{
			cities = new City[0]
		};
		Scenario scenario2 = scenario;
		string text = SerializeProject(scenario2);
		Scenario scenario3 = Json.Deserialize<Scenario>(text);
		if (scenario3.briefing != scenario2.briefing)
		{
			throw new Exception("Briefing roundtrip failed");
		}
		CreatorBriefingPanel creatorBriefingPanel = new CreatorBriefingPanel();
		creatorBriefingPanel.Size = new Size(800, 600);
		using (CreatorBriefingPanel creatorBriefingPanel2 = creatorBriefingPanel)
		{
			creatorBriefingPanel2.Editor.Text = scenario2.briefing.Replace("\r\n", "\n").Replace("\n", "\r\n");
			creatorBriefingPanel2.CreateControl();
			creatorBriefingPanel2.PerformLayout();
			if (creatorBriefingPanel2.Editor.MaxLength != 4000 || creatorBriefingPanel2.Editor.Width < 600 || creatorBriefingPanel2.Editor.Height < 300)
			{
				throw new Exception("Briefing layout too small");
			}
			using (Bitmap bitmap = new Bitmap(800, 600))
			{
				creatorBriefingPanel2.DrawToBitmap(bitmap, new Rectangle(0, 0, 800, 600));
				bitmap.Save(Path.Combine(Root, "creator-briefing.png"), ImageFormat.Png);
			}
		}
		scenario2.start_message = new StartMessage { common = "모두에게\r\n둘째 줄", per_city = new Dictionary<string, string> { { "nobody", "없는 도시" } } };
		var withStart = Json.Deserialize<Dictionary<string, object>>(SerializeProject(scenario2));
		var startRecord = (Dictionary<string, object>)withStart["start_message"];
		if ((string)startRecord["common"] != "모두에게\n둘째 줄" || startRecord.ContainsKey("per_city"))
		{
			throw new Exception("Start message was not cleaned for the file");
		}
		scenario2.start_message = new StartMessage { common = "  ", per_city = new Dictionary<string, string>() };
		if (Json.Deserialize<Dictionary<string, object>>(SerializeProject(scenario2)).ContainsKey("start_message"))
		{
			throw new Exception("Empty optional start message was not omitted");
		}
		using (CreatorBriefingPanel startPanel = new CreatorBriefingPanel { Size = new Size(800, 600) })
		{
			startPanel.CreateControl(); startPanel.ShowStartPage(); startPanel.PerformLayout();
			startPanel.StartTarget.Items.Add("모든 플레이어 (공통 글)"); startPanel.StartTarget.SelectedIndex = 0;
			startPanel.StartEditor.Text = "총독 여러분, 로마가 지켜보고 있습니다.";
			if (startPanel.StartEditor.MaxLength != 1500 || startPanel.StartEditor.Width < 600 || startPanel.StartEditor.Height < 250)
			{
				throw new Exception("Start message layout too small");
			}
			using (Bitmap bitmap = new Bitmap(800, 600))
			{
				startPanel.DrawToBitmap(bitmap, new Rectangle(0, 0, 800, 600));
				bitmap.Save(Path.Combine(Root, "creator-start-message.png"), ImageFormat.Png);
			}
		}
		scenario2.briefing = "";
		if (Json.Deserialize<Dictionary<string, object>>(SerializeProject(scenario2)).ContainsKey("briefing"))
		{
			throw new Exception("Empty optional briefing was not omitted");
		}
		File.WriteAllText(Path.Combine(Root, "briefing-probe.json"), text, new UTF8Encoding(false));
		return 0;
	}
}
internal class CreatorBriefingPanel : UserControl
{
	public readonly TextBox Editor = new TextBox
	{
		Dock = DockStyle.Fill,
		Multiline = true,
		AcceptsReturn = true,
		ScrollBars = ScrollBars.Vertical,
		MaxLength = 4000,
		Font = new Font("Malgun Gothic", 11f)
	};

	public readonly TextBox StartEditor = new TextBox
	{
		Dock = DockStyle.Fill,
		Multiline = true,
		AcceptsReturn = true,
		ScrollBars = ScrollBars.Vertical,
		MaxLength = 1500,
		Font = new Font("Malgun Gothic", 11f)
	};
	public readonly ComboBox StartTarget = new ComboBox { DropDownStyle = ComboBoxStyle.DropDownList, Width = 320 };
	public readonly Label StartHint = new Label { AutoSize = true, Padding = new Padding(12, 6, 0, 0) };
	private readonly TabControl pages = new TabControl { Dock = DockStyle.Fill };
	public void ShowStartPage() { pages.SelectedIndex = 1; }

	public CreatorBriefingPanel()
	{
		Dock = DockStyle.Fill;
		BackColor = Color.FromArgb(240, 232, 208);
		Font = new Font("Malgun Gothic", 10f);
		TableLayoutPanel tableLayoutPanel = new TableLayoutPanel
		{
			Dock = DockStyle.Fill,
			Padding = new Padding(20),
			ColumnCount = 1,
			RowCount = 3
		};
		tableLayoutPanel.RowStyles.Add(new RowStyle(SizeType.Absolute, 100f));
		tableLayoutPanel.RowStyles.Add(new RowStyle(SizeType.Percent, 100f));
		tableLayoutPanel.RowStyles.Add(new RowStyle(SizeType.Absolute, 32f));
		tableLayoutPanel.Controls.Add(new Label
		{
			Dock = DockStyle.Fill,
			Text = "게임에서 시나리오를 선택했을 때 전체 지도 옆에 표시할 설명입니다.\n배경 이야기, 도시들의 역할, 플레이 팁을 적어 주세요.\n비워 두면 설정된 목표와 시작 조건을 표시합니다.\n설명문은 승리 조건을 바꾸지 않습니다. 실제 조건은 목표 탭에서 설정하세요."
		}, 0, 0);
		Editor.AccessibleName = "시나리오 브리핑";
		tableLayoutPanel.Controls.Add(Editor, 0, 1);
		Label count = new Label
		{
			Dock = DockStyle.Fill,
			Text = "0 / 4000자"
		};
		tableLayoutPanel.Controls.Add(count, 0, 2);
		Editor.TextChanged += delegate
		{
			count.Text = Editor.Text.Length + " / 4000자";
		};
		TabPage introPage = new TabPage("시나리오 소개 (방에서 보는 글)") { BackColor = BackColor };
		introPage.Controls.Add(tableLayoutPanel);
		pages.TabPages.Add(introPage);
		TabPage startPage = new TabPage("게임 시작 메시지 (시작할 때 뜨는 글)") { BackColor = BackColor };
		TableLayoutPanel start = new TableLayoutPanel
		{
			Dock = DockStyle.Fill,
			Padding = new Padding(20),
			ColumnCount = 1,
			RowCount = 4
		};
		start.RowStyles.Add(new RowStyle(SizeType.Absolute, 76f));
		start.RowStyles.Add(new RowStyle(SizeType.Absolute, 40f));
		start.RowStyles.Add(new RowStyle(SizeType.Percent, 100f));
		start.RowStyles.Add(new RowStyle(SizeType.Absolute, 32f));
		start.Controls.Add(new Label
		{
			Dock = DockStyle.Fill,
			Text = "게임이 시작되면 각 플레이어에게 확인 창으로 한 번 뜨는 글입니다.\n공통 글을 쓰고, 필요하면 도시를 골라 그 플레이어에게만 보일 글을 덧붙이세요.\n모두 비워 두면 창이 뜨지 않습니다."
		}, 0, 0);
		FlowLayoutPanel who = new FlowLayoutPanel { Dock = DockStyle.Fill };
		who.Controls.Add(new Label { Text = "받는 사람", AutoSize = true, Padding = new Padding(0, 6, 8, 0) });
		StartTarget.AccessibleName = "게임 시작 메시지를 받는 사람";
		who.Controls.Add(StartTarget);
		who.Controls.Add(StartHint);
		start.Controls.Add(who, 0, 1);
		StartEditor.AccessibleName = "게임 시작 메시지";
		start.Controls.Add(StartEditor, 0, 2);
		Label startCount = new Label
		{
			Dock = DockStyle.Fill,
			Text = "0 / 1500자"
		};
		start.Controls.Add(startCount, 0, 3);
		StartEditor.TextChanged += delegate
		{
			startCount.Text = StartEditor.Text.Length + " / 1500자";
		};
		startPage.Controls.Add(start);
		pages.TabPages.Add(startPage);
		base.Controls.Add(pages);
	}
}

