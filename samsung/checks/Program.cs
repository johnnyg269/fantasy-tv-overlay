using System;
using System.IO;
using System.Reflection;
using System.Text.Json;

internal static class Checks
{
    private static int assertions;
    private static AlertPopupPolicy.Spec Parse(string json)
    {
        using (JsonDocument doc = JsonDocument.Parse(json)) return AlertPopupPolicy.Parse(doc.RootElement);
    }
    private static void Require(bool result, string message)
    {
        assertions++;
        if (!result) throw new Exception(message);
    }
    private static void Invalid(string json)
    {
        bool caught = false;
        try { Parse(json); } catch (InvalidDataException) { caught = true; }
        Require(caught, "invalid alert accepted: " + json);
    }
    private static FantasyOverlay.GradientParameters Gradient(string fields)
    {
        using (JsonDocument doc = JsonDocument.Parse("{\"x\":0,\"y\":0,\"width\":100,\"height\":40," + fields + "}"))
            return FantasyOverlay.ParseGradient(doc.RootElement);
    }

    private static void InvalidGradient(string json)
    {
        bool caught = false;
        try
        {
            using (JsonDocument doc = JsonDocument.Parse(json)) FantasyOverlay.ParseGradient(doc.RootElement);
        }
        catch (InvalidDataException) { caught = true; }
        Require(caught, "invalid gradient accepted: " + json);
    }

    private static int Main()
    {
        AlertPopupPolicy policy = new AlertPopupPolicy(100);
        AlertPopupPolicy.Spec first = Parse("{\"alertId\":\"first\"}");
        Require(first.DurationSeconds == 5, "default duration differs from five seconds");
        Require(policy.Apply(first, 1000), "first alert did not arm");
        Require(policy.ShouldShow(true, 1499), "alert hidden before deadline");
        Require(!policy.Apply(Parse("{\"alertId\":\"first\",\"durationSeconds\":30}"), 1400), "heartbeat rearmed");
        Require(!policy.ShouldShow(true, 1500), "same-ID duration update extended deadline");
        Require(!policy.Apply(first, 1800), "expired same-ID heartbeat rearmed");
        Require(!policy.ShouldShow(true, 1800), "expired heartbeat replayed popup");
        Require(policy.Apply(Parse("{\"alertId\":\"second\",\"durationSeconds\":1}"), 2000), "new score did not arm");
        Require(policy.ShouldShow(true, 2099), "new alert hidden early");
        Require(!policy.ShouldShow(false, 2050), "visible=false did not hide");
        Require(!policy.ShouldShow(true, 2100), "new alert failed expiry");
        policy.Apply(Parse("{}"), 2200);
        Require(policy.ShouldShow(true, 999999), "manual state did not restore legacy semantics");
        Require(!policy.ShouldShow(false, 999999), "manual hide failed");
        Invalid("{\"alertId\":123}"); Invalid("{\"alertId\":null}");
        Invalid("{\"alertId\":\"\"}"); Invalid("{\"alertId\":\"  \"}");
        Invalid("{\"alertId\":\"x\",\"durationSeconds\":0}");
        Invalid("{\"alertId\":\"x\",\"durationSeconds\":31}");
        Invalid("{\"alertId\":\"x\",\"durationSeconds\":1.5}");
        Invalid("{\"alertId\":\"x\",\"durationSeconds\":\"5\"}");
        using (JsonDocument empty = JsonDocument.Parse("{}"))
            Require(!FantasyOverlay.ReadExit(empty.RootElement), "absent exit requested shutdown");
        using (JsonDocument noExit = JsonDocument.Parse("{\"exit\":false}"))
            Require(!FantasyOverlay.ReadExit(noExit.RootElement), "exit=false requested shutdown");
        using (JsonDocument exit = JsonDocument.Parse("{\"exit\":true}"))
            Require(FantasyOverlay.ReadExit(exit.RootElement), "exit=true did not request shutdown");
        bool invalidExit = false;
        try
        {
            using (JsonDocument wrong = JsonDocument.Parse("{\"exit\":\"true\"}"))
                FantasyOverlay.ReadExit(wrong.RootElement);
        }
        catch (InvalidDataException) { invalidExit = true; }
        Require(invalidExit, "string exit accepted");
        OverlayInteractionPolicy interaction = new OverlayInteractionPolicy();
        string[] ids = { "league-a", "league-b" };
        interaction.AcceptState("alert-1", true, "league-b", ids);
        Require(interaction.SelectedLeagueId == "league-b", "popup selected league lost");
        Require(interaction.ShouldShow(true, true), "new popup hidden");
        Require(interaction.Open(), "footer could not open details");
        Require(interaction.IsExpanded, "details flag not set");
        interaction.AcceptState("alert-1", false, "league-a", ids);
        Require(interaction.ShouldShow(false, false), "host auto-hide closed details");
        Require(interaction.SelectedLeagueId == "league-b", "heartbeat changed user league");
        Require(interaction.MoveLeague(1), "league navigation failed");
        Require(interaction.SelectedLeagueId == "league-a", "league navigation failed wrap");
        interaction.AcceptState("alert-2", true, "league-b", ids);
        Require(interaction.SelectedLeagueId == "league-a", "new score switched open details");
        Require(interaction.IsExpanded, "new score closed details");
        interaction.Close();
        Require(!interaction.ShouldShow(true, true), "Back did not dismiss overlay");
        interaction.AcceptState("alert-2", true, "league-b", ids);
        Require(!interaction.ShouldShow(true, true), "heartbeat replayed closed alert");
        Require(!interaction.Open(), "dismissed footer reopened");
        interaction.AcceptState("alert-3", true, "league-b", ids);
        Require(interaction.ShouldShow(true, true), "new alert did not reset dismissal");
        Require(!interaction.ShouldShow(true, false), "expired popup remained visible");
        Require(interaction.Open(), "new alert details did not open");
        interaction.Close();
        Require(!interaction.IsExpanded, "safety close retained details");
        interaction.AcceptState(null, false, "league-a", ids);
        interaction.AcceptState(null, true, "league-a", ids);
        Require(!interaction.ShouldShow(true, true), "ordinary manual heartbeat reset dismissal");
        interaction.AcceptState(null, true, "league-a", ids, "control-1");
        Require(interaction.ShouldShow(true, true), "explicit manual presentation did not reopen");
        Require(interaction.Open(), "manual details did not open");
        interaction.AcceptState(null, false, "league-a", ids, "control-1");
        Require(interaction.ShouldShow(false, false), "same-revision auto-hide closed manual details");
        interaction.AcceptState(null, false, "league-a", ids, "control-2");
        Require(!interaction.IsExpanded && !interaction.ShouldShow(false, false), "explicit host hide did not close details");
        interaction.AcceptState(null, true, "league-a", ids, "control-3");
        interaction.Close();
        interaction.AcceptState(null, true, "league-a", ids, "control-3");
        Require(!interaction.ShouldShow(true, true), "manual heartbeat replayed dismissed popup");
        interaction.AcceptState(null, true, "league-a", ids, "control-4");
        Require(interaction.ShouldShow(true, true), "changed control revision did not reset dismissal");
        interaction.AcceptState(null, true, null, Array.Empty<string>());
        Require(!interaction.Open(), "empty sidebar list could open");
        Require(FantasyOverlay.PremultiplyChannel(255, 0) == 0, "transparent RGB did not zero");
        Require(FantasyOverlay.PremultiplyChannel(17, 0) == 0, "transparent dark RGB did not zero");
        Require(FantasyOverlay.PremultiplyChannel(255, 128) == 128, "half-alpha white was not premultiplied");
        Require(FantasyOverlay.PremultiplyChannel(17, 128) == 9, "half-alpha dark channel did not round");
        Require(FantasyOverlay.PremultiplyChannel(24, 128) == 12, "half-alpha middle channel incorrect");
        Require(FantasyOverlay.PremultiplyChannel(17, 255) == 17, "opaque RGB changed");
        Require(FantasyOverlay.PremultiplyChannel(255, 255) == 255, "opaque white changed");
        Require(FantasyOverlay.PremultiplyChannel(0, 128) == 0, "zero RGB changed");
        FantasyOverlay.GradientParameters horizontal = Gradient("\"direction\":\"horizontal\",\"start_color\":\"#FFFFFF80\",\"end_color\":\"#080C1200\"");
        Require(horizontal.VertexColors[0][0] == 128 && horizontal.VertexColors[0][3] == 128, "gradient start was not premultiplied");
        Require(horizontal.VertexColors[1][0] == 0 && horizontal.VertexColors[1][3] == 0, "transparent gradient end retained RGB");
        Require(horizontal.VertexColors[2][3] == 0 && horizontal.VertexColors[3][3] == 128, "horizontal gradient corner order incorrect");
        FantasyOverlay.GradientParameters vertical = Gradient("\"direction\":\"vertical\",\"start_color\":\"#112233FF\",\"end_color\":\"#00000000\"");
        Require(vertical.VertexColors[0][0] == 17 && vertical.VertexColors[1][0] == 17, "vertical top colors differ");
        Require(vertical.VertexColors[2][3] == 0 && vertical.VertexColors[3][3] == 0, "vertical bottom colors not transparent");
        FantasyOverlay.GradientParameters corners = Gradient("\"top_left_color\":\"#FFFFFF80\",\"top_right_color\":\"#FF000000\",\"bottom_right_color\":\"#00FF0000\",\"bottom_left_color\":\"#0000FF00\"");
        Require(corners.VertexColors[0][3] == 128 && corners.VertexColors[1][3] == 0 && corners.VertexColors[2][3] == 0 && corners.VertexColors[3][3] == 0, "four-corner alpha order incorrect");
        Require(corners.VertexColors[1][0] == 0 && corners.VertexColors[2][1] == 0 && corners.VertexColors[3][2] == 0, "four-corner transparent RGB not zero");
        InvalidGradient("{\"x\":0,\"y\":0,\"width\":0,\"height\":40,\"direction\":\"horizontal\",\"start_color\":\"#000000FF\",\"end_color\":\"#00000000\"}");
        InvalidGradient("{\"x\":0,\"y\":0,\"width\":100,\"height\":40,\"direction\":\"diagonal\",\"start_color\":\"#000000FF\",\"end_color\":\"#00000000\"}");
        InvalidGradient("{\"x\":0,\"y\":0,\"width\":100,\"height\":40,\"direction\":\"horizontal\",\"start_color\":\"bad\",\"end_color\":\"#00000000\"}");
        InvalidGradient("{\"x\":0,\"y\":0,\"width\":100,\"height\":40,\"top_left_color\":\"#000000FF\"}");
        InvalidGradient("{\"x\":0,\"y\":0,\"width\":100,\"height\":40,\"start_color\":\"#000000FF\",\"end_color\":\"#00000000\"}");
        const string sportsFont = "/home/owner/share/tmp/sdk_tools/fantasy-overlay/BarlowCondensed-ExtraBoldItalic.ttf";
        FantasyOverlay.TextFontSelection direct = FantasyOverlay.SelectTextFont(
            "Barlow Condensed ExtraBold Italic", sportsFont, true);
        Require(direct.Font == sportsFont && direct.Source == null && direct.DirectFile,
                "standalone TTF did not select Evas absolute FONT path");
        Require(!direct.MissingSource, "available font marked missing");
        FantasyOverlay.TextFontSelection inter = FantasyOverlay.SelectTextFont(
            "Inter", "/opt/usr/apps/font/QuietInter-Semibold.ttf", true);
        Require(inter.DirectFile && inter.Font.EndsWith("QuietInter-Semibold.ttf") && inter.Source == null,
                "existing Inter TTF incorrectly retained EET archive loading");
        foreach (string extension in new [] { ".otf", ".TTF", ".ttc", ".otc" })
        {
            FantasyOverlay.TextFontSelection file = FantasyOverlay.SelectTextFont("Family", "/fonts/Font" + extension, true);
            Require(file.DirectFile && file.Source == null, "standalone font type did not select file: " + extension);
        }
        FantasyOverlay.TextFontSelection archive = FantasyOverlay.SelectTextFont("EdjeFontKey", "/themes/fonts.edj", true);
        Require(archive.Source == "/themes/fonts.edj" && archive.Font == "EdjeFontKey" && !archive.DirectFile,
                "EET archive font compatibility changed");
        FantasyOverlay.TextFontSelection missing = FantasyOverlay.SelectTextFont("SamsungOne", sportsFont, false);
        Require(missing.Font == "SamsungOne" && missing.Source == null && missing.MissingSource && !missing.DirectFile,
                "missing source did not choose named-font fallback");
        FantasyOverlay.TextFontSelection named = FantasyOverlay.SelectTextFont("SamsungOne", null, false);
        Require(named.Font == "SamsungOne" && named.Source == null && !named.DirectFile && !named.MissingSource,
                "plain named font changed");
        foreach (string invalidSource in new [] { "relative.ttf", "/fonts/font\n.ttf", "/fonts/font:style=Italic.ttf", "/fonts/font,other.ttf" })
        {
            bool invalidFont = false;
            try { FantasyOverlay.SelectTextFont("Family", invalidSource, true); }
            catch (InvalidDataException) { invalidFont = true; }
            Require(invalidFont, "unsafe Evas font path accepted: " + invalidSource);
        }
        // Guard the actual legacy ABI contracts; a void setter was previously
        // declared int, so a meaningless return register rejected valid PNGs.
        const BindingFlags nativeFlags = BindingFlags.NonPublic | BindingFlags.Static;
        Require(typeof(FantasyOverlay).GetMethod("evas_object_image_file_set", nativeFlags).ReturnType == typeof(void),
                "Evas image_file_set ABI must return void");
        Require(typeof(FantasyOverlay).GetMethod("evas_object_image_load_error_get", nativeFlags).ReturnType == typeof(int),
                "Evas image_load_error_get ABI must return an int enum");
        Require(typeof(FantasyOverlay).GetMethod("evas_object_image_alpha_set", nativeFlags).GetParameters()[1].ParameterType == typeof(byte),
                "Evas image alpha flag must use Eina_Bool byte ABI");
        Require(typeof(FantasyOverlay).GetMethod("evas_object_image_smooth_scale_set", nativeFlags).GetParameters()[1].ParameterType == typeof(byte),
                "Evas image smooth flag must use Eina_Bool byte ABI");
        Console.WriteLine("Popup, interaction, font, image ABI, gradient, color and exit checks passed: " + assertions);
        return 0;
    }
}
