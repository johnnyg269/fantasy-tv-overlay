// Derived from chris-ritsen/samsung-tv-root Qn90fEflTextOverlayProbe.cs.
// Upstream source is public domain under the Unlicense; see LICENSE and NOTICE.md.
// DU8000 compatibility is unverified. Use a bounded five-second proof first.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json;
using System.Threading;

internal static class FantasyOverlay
{
    // Samsung's volume OSD uses this vendor window type together with the
    // notification-plane API below. A normal Evas layer is not sufficient to
    // place a client above tv-viewer's hardware-video composition.
    private const int ElmWinNotification = 12;
    private const int NotificationLevelTop = 40;
    private const int CanvasWidth = 1920;
    private const int CanvasHeight = 1080;
    private const int MaximumSceneBytes = 1024 * 1024;
    private const int MaximumSceneObjects = 256;
    private const string DiagnosticLogPath =
        "/home/owner/share/tmp/sdk_tools/fantasy-overlay/efl-stderr.log";
    private const int StandardErrorFileDescriptor = 2;
    private const int OpenWriteOnly = 1;
    private const int OpenCreate = 64;
    private const int OpenTruncate = 512;
    private const int OwnerReadWriteGroupAndOtherRead = 420;

    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    private delegate int EcoreTaskCallback(IntPtr data);

    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    private delegate void EcoreThreadSafeCallback(IntPtr data);

    private static readonly EcoreTaskCallback QuitCallback = QuitMainLoop;
    private static readonly EcoreThreadSafeCallback ThreadSafeQuitCallback =
        QuitMainLoopFromSignal;
    private static int quitRequested;
    private static int mainLoopRunning;
    private static string quitReason = "timer";
    private static readonly EcoreTaskCallback ReloadCallback = ReloadState;
    private static string stateFile;
    private static IntPtr overlayWindow;
    private static IntPtr overlayCanvas;
    private static SceneRenderer activeRenderer;
    private static byte[] appliedBytes;
    private static int staleSeconds = 30;
    private static string activeMode = "compact";
    private static bool visible;
    private static bool hasState;
    private static string lastStateError;
    private static readonly AlertPopupPolicy PopupPolicy = new AlertPopupPolicy(Stopwatch.Frequency);
    private static readonly OverlayInteractionPolicy Interaction = new OverlayInteractionPolicy();
    private static readonly Dictionary<string, JsonElement> SidebarScenes = new Dictionary<string, JsonElement>(StringComparer.Ordinal);
    private static JsonElement compactScene;
    private static bool haveCompactScene;
    private static bool interactiveAllowed = true;
    private static bool inputReady;
    private static IntPtr waylandWindow;
    private static IntPtr inputLibrary;
    private static bool opaqueRegionApiAvailable = true;
    private static bool opaqueRegionInitialized;
    private static string lastOpaqueRegionMode;
    private static IntPtr keyDownHandler;
    private static IntPtr keyUpHandler;
    private static readonly HashSet<string> grabbedKeys = new HashSet<string>(StringComparer.Ordinal);
    private static readonly HashSet<string> pressedKeys = new HashSet<string>(StringComparer.Ordinal);
    private static readonly Dictionary<string, long> deferredRelease = new Dictionary<string, long>(StringComparer.Ordinal);
    private static readonly Dictionary<string, int> failedGrabs = new Dictionary<string, int>(StringComparer.Ordinal);
    private static readonly string[] PopupKeys = { "Return", "KP_Enter" };
    private static readonly string[] SidebarKeys = { "Return", "KP_Enter", "XF86Back", "Back", "Escape", "Left", "Right", "Up", "Down" };

    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    private delegate byte EcoreKeyCallback(IntPtr data, int type, IntPtr eventInfo);
    private static readonly EcoreKeyCallback KeyDownCallback = OnKeyDown;
    private static readonly EcoreKeyCallback KeyUpCallback = OnKeyUp;

    [DllImport("libc.so.6", CallingConvention = CallingConvention.Cdecl, SetLastError = true)]
    private static extern int open(string path, int flags, int mode);

    [DllImport("libc.so.6", CallingConvention = CallingConvention.Cdecl, SetLastError = true)]
    private static extern int dup(int fileDescriptor);

    [DllImport("libc.so.6", CallingConvention = CallingConvention.Cdecl, SetLastError = true)]
    private static extern int dup2(int oldFileDescriptor, int newFileDescriptor);

    [DllImport("libc.so.6", CallingConvention = CallingConvention.Cdecl)]
    private static extern int close(int fileDescriptor);

    [DllImport("libc.so.6", CallingConvention = CallingConvention.Cdecl)]
    private static extern int fflush(IntPtr stream);

    [DllImport("libelementary.so.1", CallingConvention = CallingConvention.Cdecl)]
    private static extern int elm_init(int argc, IntPtr argv);

    [DllImport("libelementary.so.1", CallingConvention = CallingConvention.Cdecl)]
    private static extern int elm_shutdown();

    [DllImport("libelementary.so.1", CallingConvention = CallingConvention.Cdecl)]
    private static extern IntPtr elm_win_wl_window_get(IntPtr window);

    // Tizen EFL 1.25.1 Ecore_Wl2.h: modifiers are int, and TOPMOST is 2.
    [DllImport("libecore_wl2.so.1", CallingConvention = CallingConvention.Cdecl)]
    private static extern byte ecore_wl2_window_keygrab_set(IntPtr window, string key, int modifiers, int notModifiers, int priority, int mode);

    [DllImport("libecore_wl2.so.1", CallingConvention = CallingConvention.Cdecl)]
    private static extern byte ecore_wl2_window_keygrab_unset(IntPtr window, string key, int modifiers, int anyModifiers);

    [DllImport("libecore_wl2.so.1", CallingConvention = CallingConvention.Cdecl)]
    private static extern void ecore_wl2_window_opaque_region_set(IntPtr window, int x, int y, int width, int height);

    [DllImport("libecore.so.1", CallingConvention = CallingConvention.Cdecl)]
    private static extern IntPtr ecore_event_handler_add(int type, EcoreKeyCallback callback, IntPtr data);

    [DllImport("libecore.so.1", CallingConvention = CallingConvention.Cdecl)]
    private static extern IntPtr ecore_event_handler_del(IntPtr handler);

    [DllImport("libelementary.so.1", CallingConvention = CallingConvention.Cdecl)]
    private static extern IntPtr elm_win_add(IntPtr parent, string name, int type);

    [DllImport("libelementary.so.1", CallingConvention = CallingConvention.Cdecl)]
    private static extern void elm_win_alpha_set(IntPtr window, int alpha);

    [DllImport("libelementary.so.1", CallingConvention = CallingConvention.Cdecl)]
    private static extern void elm_win_borderless_set(IntPtr window, int borderless);

    [DllImport("libelementary.so.1", CallingConvention = CallingConvention.Cdecl)]
    private static extern int elm_win_aux_hint_add(IntPtr window, string hint, string value);

    [DllImport("libelementary.so.1", CallingConvention = CallingConvention.Cdecl)]
    private static extern void elm_win_layer_set(IntPtr window, int layer);

    [DllImport("libelementary.so.1", CallingConvention = CallingConvention.Cdecl)]
    private static extern void elm_win_input_rect_set(IntPtr window, int x, int y, int width, int height);

    [DllImport("libelementary.so.1", CallingConvention = CallingConvention.Cdecl)]
    private static extern void elm_win_prop_focus_skip_set(IntPtr window, int skip);

    [DllImport("libcapi-ui-efl-util.so.0", CallingConvention = CallingConvention.Cdecl)]
    private static extern int efl_util_set_notification_window_level(IntPtr window, int level);

    [DllImport("libevas.so.1", CallingConvention = CallingConvention.Cdecl)]
    private static extern IntPtr evas_object_evas_get(IntPtr obj);

    [DllImport("libevas.so.1", CallingConvention = CallingConvention.Cdecl)]
    private static extern IntPtr evas_object_rectangle_add(IntPtr evas);

    [DllImport("libevas.so.1", CallingConvention = CallingConvention.Cdecl)]
    private static extern IntPtr evas_object_text_add(IntPtr evas);

    [DllImport("libevas.so.1", CallingConvention = CallingConvention.Cdecl)]
    private static extern IntPtr evas_object_textblock_add(IntPtr evas);

    [DllImport("libevas.so.1", CallingConvention = CallingConvention.Cdecl)]
    private static extern IntPtr evas_textblock_style_new();

    [DllImport("libevas.so.1", CallingConvention = CallingConvention.Cdecl)]
    private static extern int evas_textblock_style_set(IntPtr style, string value);

    [DllImport("libevas.so.1", CallingConvention = CallingConvention.Cdecl)]
    private static extern void evas_object_textblock_style_set(IntPtr obj, IntPtr style);

    [DllImport("libevas.so.1", CallingConvention = CallingConvention.Cdecl)]
    private static extern void evas_object_textblock_text_markup_set(IntPtr obj, string markup);

    [DllImport("libevas.so.1", CallingConvention = CallingConvention.Cdecl)]
    private static extern void evas_object_textblock_size_formatted_get(
        IntPtr obj,
        out int width,
        out int height);

    [DllImport("libevas.so.1", CallingConvention = CallingConvention.Cdecl)]
    private static extern IntPtr evas_object_line_add(IntPtr evas);

    [DllImport("libevas.so.1", CallingConvention = CallingConvention.Cdecl)]
    private static extern IntPtr evas_object_polygon_add(IntPtr evas);

    [DllImport("libevas.so.1", CallingConvention = CallingConvention.Cdecl)]
    private static extern IntPtr evas_object_image_add(IntPtr evas);

    [DllImport("libevas.so.1", CallingConvention = CallingConvention.Cdecl)]
    private static extern void evas_object_text_font_set(IntPtr obj, string font, int size);

    [DllImport("libevas.so.1", CallingConvention = CallingConvention.Cdecl)]
    private static extern void evas_object_text_font_source_set(IntPtr obj, string fontSource);

    [DllImport("libevas.so.1", CallingConvention = CallingConvention.Cdecl)]
    private static extern void evas_object_text_text_set(IntPtr obj, string text);

    [DllImport("libevas.so.1", CallingConvention = CallingConvention.Cdecl)]
    private static extern int evas_object_text_horiz_advance_get(IntPtr obj);

    [DllImport("libevas.so.1", CallingConvention = CallingConvention.Cdecl)]
    private static extern void evas_object_geometry_get(
        IntPtr obj, out int x, out int y, out int width, out int height);

    [DllImport("libevas.so.1", CallingConvention = CallingConvention.Cdecl)]
    private static extern void evas_object_line_xy_set(
        IntPtr obj,
        int x1,
        int y1,
        int x2,
        int y2);

    [DllImport("libevas.so.1", CallingConvention = CallingConvention.Cdecl)]
    private static extern void evas_object_polygon_point_add(IntPtr obj, int x, int y);

    [DllImport("libevas.so.1", CallingConvention = CallingConvention.Cdecl)]
    private static extern void evas_object_image_file_set(
        IntPtr obj,
        string file,
        string key);

    [DllImport("libevas.so.1", CallingConvention = CallingConvention.Cdecl)]
    private static extern int evas_object_image_load_error_get(IntPtr obj);

    [DllImport("libevas.so.1", CallingConvention = CallingConvention.Cdecl)]
    private static extern void evas_object_image_alpha_set(IntPtr obj, byte alpha);

    [DllImport("libevas.so.1", CallingConvention = CallingConvention.Cdecl)]
    private static extern void evas_object_image_fill_set(
        IntPtr obj,
        int x,
        int y,
        int width,
        int height);

    [DllImport("libevas.so.1", CallingConvention = CallingConvention.Cdecl)]
    private static extern void evas_object_image_smooth_scale_set(IntPtr obj, byte smoothScale);

    [DllImport("libevas.so.1", CallingConvention = CallingConvention.Cdecl)]
    private static extern void evas_object_color_set(IntPtr obj, int red, int green, int blue, int alpha);

    [DllImport("libevas.so.1", CallingConvention = CallingConvention.Cdecl)]
    private static extern void evas_object_pass_events_set(IntPtr obj, int passEvents);

    [DllImport("libevas.so.1", CallingConvention = CallingConvention.Cdecl)]
    private static extern void evas_object_clip_set(IntPtr obj, IntPtr clipper);

    [DllImport("libevas.so.1", CallingConvention = CallingConvention.Cdecl)]
    private static extern IntPtr evas_map_new(int count);

    [DllImport("libevas.so.1", CallingConvention = CallingConvention.Cdecl)]
    private static extern void evas_map_util_points_populate_from_geometry(IntPtr map, int x, int y, int width, int height, int z);

    [DllImport("libevas.so.1", CallingConvention = CallingConvention.Cdecl)]
    private static extern void evas_map_point_color_set(IntPtr map, int index, int red, int green, int blue, int alpha);

    [DllImport("libevas.so.1", CallingConvention = CallingConvention.Cdecl)]
    private static extern void evas_map_alpha_set(IntPtr map, byte enabled);

    [DllImport("libevas.so.1", CallingConvention = CallingConvention.Cdecl)]
    private static extern void evas_map_smooth_set(IntPtr map, byte enabled);

    [DllImport("libevas.so.1", CallingConvention = CallingConvention.Cdecl)]
    private static extern void evas_object_map_set(IntPtr obj, IntPtr map);

    [DllImport("libevas.so.1", CallingConvention = CallingConvention.Cdecl)]
    private static extern void evas_object_map_enable_set(IntPtr obj, byte enabled);

    [DllImport("libevas.so.1", CallingConvention = CallingConvention.Cdecl)]
    private static extern void evas_map_free(IntPtr map);

    [DllImport("libevas.so.1", CallingConvention = CallingConvention.Cdecl)]
    private static extern void evas_object_move(IntPtr obj, int x, int y);

    [DllImport("libevas.so.1", CallingConvention = CallingConvention.Cdecl)]
    private static extern void evas_object_resize(IntPtr obj, int width, int height);

    [DllImport("libevas.so.1", CallingConvention = CallingConvention.Cdecl)]
    private static extern void evas_object_show(IntPtr obj);

    [DllImport("libevas.so.1", CallingConvention = CallingConvention.Cdecl)]
    private static extern void evas_object_hide(IntPtr obj);

    [DllImport("libevas.so.1", CallingConvention = CallingConvention.Cdecl)]
    private static extern void evas_object_del(IntPtr obj);

    [DllImport("libevas.so.1", CallingConvention = CallingConvention.Cdecl)]
    private static extern void evas_textblock_style_free(IntPtr style);

    [DllImport("libecore.so.1", CallingConvention = CallingConvention.Cdecl)]
    private static extern IntPtr ecore_timer_add(double seconds, EcoreTaskCallback callback, IntPtr data);

    [DllImport("libecore.so.1", CallingConvention = CallingConvention.Cdecl)]
    private static extern void ecore_main_loop_begin();

    [DllImport("libecore.so.1", CallingConvention = CallingConvention.Cdecl)]
    private static extern void ecore_main_loop_quit();

    [DllImport("libecore.so.1", CallingConvention = CallingConvention.Cdecl)]
    private static extern void ecore_main_loop_thread_safe_call_async(
        EcoreThreadSafeCallback callback,
        IntPtr data);

    private static int Main(string[] arguments)
    {
        int seconds = 5;
        string message = "FANTASY OVERLAY TEST";
        string scenePath = null;
        bool messageSpecified = false;
        bool verboseEfl = false;

        for (int index = 0; index < arguments.Length; index++)
        {
            if (arguments[index] == "--seconds" && index + 1 < arguments.Length)
            {
                if (!int.TryParse(arguments[++index], NumberStyles.Integer, CultureInfo.InvariantCulture, out seconds)
                    || seconds < 1 || seconds > 86400)
                {
                    Console.Error.WriteLine("--seconds must be an integer from 1 through 86400");
                    return 2;
                }
            }
            else if (arguments[index] == "--message" && index + 1 < arguments.Length)
            {
                message = arguments[++index];
                messageSpecified = true;
            }
            else if (arguments[index] == "--scene" && index + 1 < arguments.Length)
            {
                scenePath = arguments[++index];
            }
            else if (arguments[index] == "--state" && index + 1 < arguments.Length)
            {
                stateFile = arguments[++index];
            }
            else if (arguments[index] == "--stale-seconds" && index + 1 < arguments.Length)
            {
                if (!int.TryParse(arguments[++index], out staleSeconds)
                    || staleSeconds < 2 || staleSeconds > 3600)
                {
                    Console.Error.WriteLine("--stale-seconds must be an integer from 2 through 3600");
                    return 2;
                }
            }
            else if (arguments[index] == "--no-interactive")
            {
                interactiveAllowed = false;
            }
            else if (arguments[index] == "--verbose-efl")
            {
                verboseEfl = true;
            }
            else
            {
                PrintUsage();
                return 2;
            }
        }

        if ((scenePath != null && messageSpecified)
            || (stateFile != null && (scenePath != null || messageSpecified)))
        {
            Console.Error.WriteLine("--state, --scene and --message are mutually exclusive");
            return 2;
        }
        if (message.Length > 4096)
        {
            Console.Error.WriteLine("--message must not exceed 4096 characters");
            return 2;
        }

        Volatile.Write(ref quitRequested, 0);
        Volatile.Write(ref mainLoopRunning, 0);
        quitReason = "timer";

        NativeDiagnostics diagnostics;
        try
        {
            diagnostics = NativeDiagnostics.Start(verboseEfl);
        }
        catch (IOException error)
        {
            Console.Error.WriteLine("could not open EFL diagnostic log: {0}", error.Message);
            return 1;
        }

        ConfigureUiEnvironment();
        int initResult = elm_init(0, IntPtr.Zero);
        Console.WriteLine("elm_init={0}", initResult);

        IntPtr window = elm_win_add(IntPtr.Zero, "fantasy-score-overlay", ElmWinNotification);
        if (window == IntPtr.Zero)
        {
            diagnostics.Restore();
            Console.Error.WriteLine("elm_win_add failed");
            return 1;
        }

        elm_win_alpha_set(window, 1);
        elm_win_borderless_set(window, 1);
        elm_win_prop_focus_skip_set(window, 1);
        int notificationResult = efl_util_set_notification_window_level(
            window,
            NotificationLevelTop);
        elm_win_layer_set(window, 900);
        elm_win_input_rect_set(window, 0, 0, 0, 0);
        int effectHint = elm_win_aux_hint_add(window, "wm.comp.win.effect.enable", "0");
        evas_object_move(window, 0, 0);
        evas_object_resize(window, CanvasWidth, CanvasHeight);

        IntPtr evas = evas_object_evas_get(window);
        if (evas == IntPtr.Zero)
        {
            diagnostics.Restore();
            Console.Error.WriteLine("evas_object_evas_get failed");
            return 1;
        }

        overlayWindow = window;
        overlayCanvas = evas;
        if (stateFile != null && interactiveAllowed) SetupKeyInput();
        int objectCount = 0;
        if (stateFile == null)
        {
            activeRenderer = new SceneRenderer(evas);
            try
            {
                objectCount = scenePath == null
                    ? activeRenderer.RenderDefaultBanner(message)
                    : activeRenderer.RenderSceneFile(scenePath);
                activeRenderer.ShowAll();
                SetVisible(true);
            }
            catch (Exception error) when (IsStateError(error))
            {
                activeRenderer.Dispose();
                diagnostics.Restore();
                Console.Error.WriteLine("scene_error: {0}", error.Message);
                return 2;
            }
        }
        else
        {
            ReloadState(IntPtr.Zero);
            ecore_timer_add(0.5, ReloadCallback, IntPtr.Zero);
            objectCount = activeRenderer == null ? 0 : activeRenderer.ObjectCount;
        }

        evas_object_pass_events_set(window, 1);
        Console.WriteLine(
            "overlay_ready duration_s={0} geometry=0,0 {1}x{2} objects={3} effect_hint_id={4} notification_result={5} efl_log={6} visible={7} mode={8}",
            seconds, CanvasWidth, CanvasHeight, objectCount, effectHint,
            notificationResult, diagnostics.LogPath ?? "stderr", visible, activeMode);
        Console.Out.Flush();

        Console.CancelKeyPress += OnCancelKeyPress;
        if (seconds > 0)
        {
            ecore_timer_add(seconds, QuitCallback, IntPtr.Zero);
        }
        Volatile.Write(ref mainLoopRunning, 1);
        if (Volatile.Read(ref quitRequested) != 0)
        {
            ecore_main_loop_thread_safe_call_async(
                ThreadSafeQuitCallback,
                IntPtr.Zero);
        }
        ecore_main_loop_begin();
        Volatile.Write(ref mainLoopRunning, 0);
        Console.CancelKeyPress -= OnCancelKeyPress;

        // This vendor notification window double-unrefs internal EO objects
        // when deleted in a short-lived raw Elementary client. Hide it and let
        // normal process exit close the Evas canvas and Wayland connection.
        visible = false;
        UpdateOpaqueRegion(true);
        ReleaseAllKeyGrabs();
        RemoveKeyInput();
        evas_object_hide(window);
        diagnostics.Restore();
        Console.WriteLine("overlay_done reason={0}", quitReason);
        activeRenderer?.Dispose();
        activeRenderer = null;
        GC.KeepAlive(ReloadCallback);
        return 0;
    }

    private static void PrintUsage()
    {
        Console.Error.WriteLine(
            "usage: FantasyOverlay [--seconds 1..86400] [--stale-seconds 2..3600] [--no-interactive] [--verbose-efl] "
            + "([--message text] | [--scene scene.json] | [--state state.json])");
    }

    private static bool IsStateError(Exception error)
    {
        return error is IOException || error is UnauthorizedAccessException
            || error is JsonException || error is InvalidDataException
            || error is ArgumentException || error is InvalidOperationException;
    }

    // Runs only on the Ecore UI thread; host writes must use atomic rename.
    private static int ReloadState(IntPtr data)
    {
        try
        {
            FileInfo file = new FileInfo(stateFile);
            if (!file.Exists)
                throw new FileNotFoundException("state file is missing", stateFile);
            if (file.Length < 2 || file.Length > MaximumSceneBytes)
                throw new InvalidDataException("state file size is outside 2..1048576 bytes");
            double age = (DateTime.UtcNow - file.LastWriteTimeUtc).TotalSeconds;
            if (age > staleSeconds || age < -5)
            {
                Interaction.Close();
                SetVisible(false);
                LogStateError("state heartbeat expired or has a future timestamp");
                return 1;
            }
            byte[] bytes = File.ReadAllBytes(stateFile);
            if (SameBytes(appliedBytes, bytes))
            {
                // A valid heartbeat can recover a previously hidden stale frame.
                if (hasState)
                {
                    using (JsonDocument document = JsonDocument.Parse(bytes))
                        ApplyPopupVisibility(ReadVisible(document.RootElement));
                }
                lastStateError = null;
                return 1;
            }
            using (JsonDocument document = JsonDocument.Parse(bytes))
            {
                JsonElement root = document.RootElement;
                if (root.ValueKind != JsonValueKind.Object)
                    throw new InvalidDataException("state must be an object");
                if (ReadExit(root))
                {
                    Interaction.Close();
                    SetVisible(false);
                    RequestQuit("state-exit");
                    return 1;
                }
                bool shouldShow = ReadVisible(root);
                AlertPopupPolicy.Spec alert = AlertPopupPolicy.Parse(root);
                string mode = "compact";
                if (root.TryGetProperty("mode", out JsonElement modeValue))
                {
                    if (modeValue.ValueKind != JsonValueKind.String)
                        throw new InvalidDataException("mode must be a string");
                    mode = modeValue.GetString();
                }
                if (mode != "compact" && mode != "expanded")
                    throw new InvalidDataException("mode must be compact or expanded");
                JsonElement scene = root.TryGetProperty("scene", out JsonElement nested)
                    ? nested : root;
                bool hasObjects = scene.ValueKind == JsonValueKind.Object
                    && scene.TryGetProperty("objects", out JsonElement ignored);
                if (shouldShow && !hasObjects)
                    throw new InvalidDataException("visible state requires scene.objects");

                Dictionary<string, JsonElement> updatedSidebars = ReadSidebarScenes(root);
                if (updatedSidebars != null)
                {
                    SidebarScenes.Clear();
                    foreach (KeyValuePair<string, JsonElement> entry in updatedSidebars)
                        SidebarScenes.Add(entry.Key, entry.Value);
                }
                if (hasObjects)
                {
                    compactScene = scene.Clone();
                    haveCompactScene = true;
                }
                string requestedLeague = root.TryGetProperty("selectedLeagueId", out JsonElement selected)
                    ? ReadLeagueId(selected) : null;
                string controlRevision = null;
                if (root.TryGetProperty("controlRevision", out JsonElement revision))
                {
                    if (revision.ValueKind != JsonValueKind.String && revision.ValueKind != JsonValueKind.Number)
                        throw new InvalidDataException("controlRevision must be a string or number");
                    controlRevision = revision.GetRawText();
                    if (controlRevision.Length > 256)
                        throw new InvalidDataException("controlRevision must contain at most 256 characters");
                }
                Interaction.AcceptState(alert.Id, shouldShow, requestedLeague, SidebarScenes.Keys, controlRevision);
                if (Interaction.IsExpanded || hasObjects) RenderCurrentScene(mode);
                hasState = true;
                appliedBytes = bytes;
                if (PopupPolicy.Apply(alert, Stopwatch.GetTimestamp()))
                {
                    Console.WriteLine("overlay_alert id={0} duration_s={1}",
                        JsonSerializer.Serialize(alert.Id), alert.DurationSeconds);
                }
                ApplyPopupVisibility(shouldShow);
                lastStateError = null;
                Console.WriteLine("overlay_state visible={0} mode={1} objects={2}",
                    visible, activeMode, activeRenderer == null ? 0 : activeRenderer.ObjectCount);
                Console.Out.Flush();
            }
        }
        catch (Exception error) when (IsStateError(error))
        {
            // Hide on invalid or missing updates. Do not leave an old score on screen.
            Interaction.Close();
            SetVisible(false);
            LogStateError(error.Message);
        }
        return 1;
    }

    private static void ApplyPopupVisibility(bool requested)
    {
        bool allowed = Interaction.ShouldShow(requested, PopupPolicy.ShouldShow(requested, Stopwatch.GetTimestamp()));
        if (visible && requested && !allowed && !Interaction.IsDismissed)
        {
            Console.WriteLine("overlay_popup_expired");
            Console.Out.Flush();
        }
        SetVisible(allowed);
    }

    internal static bool ReadExit(JsonElement root)
    {
        if (!root.TryGetProperty("exit", out JsonElement value)) return false;
        if (value.ValueKind != JsonValueKind.True && value.ValueKind != JsonValueKind.False)
            throw new InvalidDataException("exit must be boolean");
        return value.GetBoolean();
    }

    private static bool ReadVisible(JsonElement root)
    {
        if (!root.TryGetProperty("visible", out JsonElement value)) return true;
        if (value.ValueKind != JsonValueKind.True && value.ValueKind != JsonValueKind.False)
            throw new InvalidDataException("visible must be boolean");
        return value.GetBoolean();
    }

    internal sealed class GradientParameters
    {
        internal int X;
        internal int Y;
        internal int Width;
        internal int Height;
        // Evas map order is top-left, top-right, bottom-right, bottom-left.
        internal int[][] VertexColors;
    }

    internal static GradientParameters ParseGradient(JsonElement item)
    {
        if (item.ValueKind != JsonValueKind.Object)
            throw new InvalidDataException("gradient must be an object");
        GradientParameters result = new GradientParameters
        {
            X = GradientInteger(item, "x", -8192, 8192),
            Y = GradientInteger(item, "y", -8192, 8192),
            Width = GradientInteger(item, "width", 1, 8192),
            Height = GradientInteger(item, "height", 1, 8192),
        };
        string[] cornerNames = { "top_left_color", "top_right_color", "bottom_right_color", "bottom_left_color" };
        int cornerCount = 0;
        foreach (string name in cornerNames) if (item.TryGetProperty(name, out JsonElement ignored)) cornerCount++;
        if (cornerCount != 0 && cornerCount != 4)
            throw new InvalidDataException("gradient requires all four corner colors together");
        Rgba[] colors = new Rgba[4];
        if (cornerCount == 4)
        {
            for (int index = 0; index < 4; index++) colors[index] = GradientColor(item, cornerNames[index]);
        }
        else
        {
            if (!item.TryGetProperty("direction", out JsonElement directionValue)
                || directionValue.ValueKind != JsonValueKind.String)
                throw new InvalidDataException("gradient direction must be horizontal or vertical");
            string direction = directionValue.GetString();
            if (direction != "horizontal" && direction != "vertical")
                throw new InvalidDataException("gradient direction must be horizontal or vertical");
            Rgba first = GradientColor(item, "start_color");
            Rgba last = GradientColor(item, "end_color");
            colors[0] = first;
            colors[1] = direction == "horizontal" ? last : first;
            colors[2] = last;
            colors[3] = direction == "horizontal" ? first : last;
        }
        result.VertexColors = new int[4][];
        for (int index = 0; index < 4; index++)
        {
            Rgba color = colors[index];
            result.VertexColors[index] = new[]
            {
                PremultiplyChannel(color.Red, color.Alpha),
                PremultiplyChannel(color.Green, color.Alpha),
                PremultiplyChannel(color.Blue, color.Alpha),
                color.Alpha,
            };
        }
        return result;
    }

    private static int GradientInteger(JsonElement item, string name, int minimum, int maximum)
    {
        if (!item.TryGetProperty(name, out JsonElement value)
            || value.ValueKind != JsonValueKind.Number || !value.TryGetInt32(out int result)
            || result < minimum || result > maximum)
            throw new InvalidDataException("gradient " + name + " must be an integer in " + minimum + ".." + maximum);
        return result;
    }

    private static Rgba GradientColor(JsonElement item, string name)
    {
        if (!item.TryGetProperty(name, out JsonElement value) || value.ValueKind != JsonValueKind.String)
            throw new InvalidDataException("gradient " + name + " must be a color string");
        return Rgba.Parse(value.GetString() ?? string.Empty, name);
    }

    internal static int PremultiplyChannel(int channel, int alpha)
    {
        if (channel < 0 || channel > 255) throw new ArgumentOutOfRangeException(nameof(channel));
        if (alpha < 0 || alpha > 255) throw new ArgumentOutOfRangeException(nameof(alpha));
        return (channel * alpha + 127) / 255;
    }

    internal static string ValidateFontSource(string value)
    {
        if (value == null) return null;
        if (value.Length < 1 || value.Length > 4096 || value[0] != '/')
            throw new InvalidDataException("fontSource must be an absolute POSIX path of 1..4096 characters");
        foreach (char character in value)
            if (char.IsControl(character))
                throw new InvalidDataException("fontSource must not contain control characters");
        return value;
    }

    internal readonly struct TextFontSelection
    {
        internal readonly string Font;
        internal readonly string Source;
        internal readonly bool DirectFile;
        internal readonly bool MissingSource;

        internal TextFontSelection(string font, string source, bool directFile, bool missingSource)
        {
            Font = font;
            Source = source;
            DirectFile = directFile;
            MissingSource = missingSource;
        }
    }

    internal static TextFontSelection SelectTextFont(string font, string fontSource, bool sourceAvailable)
    {
        fontSource = ValidateFontSource(fontSource);
        if (fontSource == null) return new TextFontSelection(font, null, false, false);
        if (!sourceAvailable) return new TextFontSelection(font, null, false, true);

        string extension = Path.GetExtension(fontSource);
        bool standalone = extension.Equals(".ttf", StringComparison.OrdinalIgnoreCase)
            || extension.Equals(".otf", StringComparison.OrdinalIgnoreCase)
            || extension.Equals(".ttc", StringComparison.OrdinalIgnoreCase)
            || extension.Equals(".otc", StringComparison.OrdinalIgnoreCase);
        if (standalone)
        {
            // Evas 1.25.1 evas_font_load opens font_source as an EET archive.
            // Its absolute FONT-name branch instead calls the FreeType loader
            // directly. Do not pass a standalone TTF as an archive source.
            // Evas parses ':' as style attributes and ',' as fallback fonts;
            // reject those delimiters rather than silently selecting a family.
            if (fontSource.IndexOf(':') >= 0 || fontSource.IndexOf(',') >= 0)
                throw new InvalidDataException("standalone font path must not contain ':' or ','");
            return new TextFontSelection(fontSource, null, true, false);
        }
        return new TextFontSelection(font, fontSource, false, false);
    }

    private static bool SameBytes(byte[] first, byte[] second)
    {
        if (first == null || first.Length != second.Length) return false;
        for (int index = 0; index < first.Length; index++)
            if (first[index] != second[index]) return false;
        return true;
    }

    private static void SetVisible(bool value)
    {
        bool changed = value != visible;
        visible = value;
        UpdateOpaqueRegion();
        if (changed)
        {
            if (value) evas_object_show(overlayWindow);
            else evas_object_hide(overlayWindow);
        }
        SynchronizeKeyGrabs();
    }

    private static void UpdateOpaqueRegion(bool forceClear = false)
    {
        if (!opaqueRegionApiAvailable || overlayWindow == IntPtr.Zero) return;
        string mode = forceClear || !visible ? "hidden"
            : Interaction.IsExpanded ? "sidebar-glass" : "popup";
        if (opaqueRegionInitialized && mode == lastOpaqueRegionMode) return;
        try
        {
            if (waylandWindow == IntPtr.Zero) waylandWindow = elm_win_wl_window_get(overlayWindow);
            if (waylandWindow == IntPtr.Zero)
            {
                Console.Error.WriteLine("overlay_opaque_region result=unavailable fallback=scene-alpha");
                opaqueRegionApiAvailable = false;
                return;
            }
            // Both popup and sidebar use per-pixel alpha. Never declare an opaque region.
            ecore_wl2_window_opaque_region_set(waylandWindow, 0, 0, 0, 0);
            opaqueRegionInitialized = true;
            lastOpaqueRegionMode = mode;
            Console.WriteLine("overlay_opaque_region mode={0} region=0,0,0,0 result=clear-requested", mode);
            Console.Out.Flush();
        }
        catch (Exception error) when (error is DllNotFoundException || error is EntryPointNotFoundException)
        {
            opaqueRegionApiAvailable = false;
            Console.Error.WriteLine("overlay_opaque_region result=unavailable fallback=scene-alpha detail={0}", error.Message);
        }
    }

    private static Dictionary<string, JsonElement> ReadSidebarScenes(JsonElement root)
    {
        if (!root.TryGetProperty("sidebarScenes", out JsonElement list)) return null;
        if (list.ValueKind != JsonValueKind.Array || list.GetArrayLength() > 16)
            throw new InvalidDataException("sidebarScenes must be an array with at most 16 entries");
        Dictionary<string, JsonElement> result = new Dictionary<string, JsonElement>(StringComparer.Ordinal);
        foreach (JsonElement entry in list.EnumerateArray())
        {
            if (entry.ValueKind != JsonValueKind.Object
                || !entry.TryGetProperty("leagueId", out JsonElement id)
                || !entry.TryGetProperty("scene", out JsonElement value)
                || value.ValueKind != JsonValueKind.Object
                || !value.TryGetProperty("objects", out JsonElement objects)
                || objects.ValueKind != JsonValueKind.Array
                || objects.GetArrayLength() < 1 || objects.GetArrayLength() > MaximumSceneObjects)
                throw new InvalidDataException("sidebarScenes entries require leagueId and scene.objects");
            string key = ReadLeagueId(id);
            if (!result.TryAdd(key, value.Clone()))
                throw new InvalidDataException("sidebarScenes contains a duplicate leagueId");
        }
        return result;
    }

    private static string ReadLeagueId(JsonElement value)
    {
        string result = value.ValueKind == JsonValueKind.String ? value.GetString()
            : value.ValueKind == JsonValueKind.Number ? value.GetRawText() : null;
        if (string.IsNullOrWhiteSpace(result) || result.Length > 128)
            throw new InvalidDataException("leagueId must be a nonempty string or number of at most 128 characters");
        return result;
    }

    private static void RenderCurrentScene(string compactMode = "compact")
    {
        JsonElement target;
        if (Interaction.IsExpanded)
        {
            if (!SidebarScenes.TryGetValue(Interaction.SelectedLeagueId ?? string.Empty, out target))
                throw new InvalidDataException("selected sidebar scene is missing");
        }
        else
        {
            if (!haveCompactScene) throw new InvalidDataException("compact scene is missing");
            target = compactScene;
        }
        SceneRenderer next = new SceneRenderer(overlayCanvas);
        try { next.RenderScene(target); }
        catch { next.Dispose(); throw; }
        SceneRenderer previous = activeRenderer;
        activeRenderer = next;
        activeRenderer.ShowAll();
        previous?.Dispose();
        activeMode = Interaction.IsExpanded ? "expanded" : compactMode;
    }

    private static void SetupKeyInput()
    {
        try
        {
            waylandWindow = elm_win_wl_window_get(overlayWindow);
            if (waylandWindow == IntPtr.Zero) throw new InvalidOperationException("Wayland window is unavailable");
            inputLibrary = NativeLibrary.Load("libecore_input.so.1");
            int down = Marshal.ReadInt32(NativeLibrary.GetExport(inputLibrary, "ECORE_EVENT_KEY_DOWN"));
            int up = Marshal.ReadInt32(NativeLibrary.GetExport(inputLibrary, "ECORE_EVENT_KEY_UP"));
            if (down <= 0 || up <= 0) throw new InvalidOperationException("Ecore key event types are uninitialized");
            keyDownHandler = ecore_event_handler_add(down, KeyDownCallback, IntPtr.Zero);
            keyUpHandler = ecore_event_handler_add(up, KeyUpCallback, IntPtr.Zero);
            if (keyDownHandler == IntPtr.Zero || keyUpHandler == IntPtr.Zero)
                throw new InvalidOperationException("could not register Ecore key handlers");
            inputReady = true;
            Console.WriteLine("overlay_interaction ready backend=tizen-wayland mode=topmost");
        }
        catch (Exception error) when (error is DllNotFoundException || error is EntryPointNotFoundException
            || error is InvalidOperationException || error is BadImageFormatException)
        {
            Console.Error.WriteLine("overlay_interaction unavailable: {0}", error.Message);
            RemoveKeyInput();
        }
    }

    private static void SynchronizeKeyGrabs()
    {
        if (!inputReady) return;
        HashSet<string> desired = new HashSet<string>(StringComparer.Ordinal);
        if (visible && interactiveAllowed && SidebarScenes.Count > 0)
            foreach (string key in Interaction.IsExpanded ? SidebarKeys : PopupKeys) desired.Add(key);
        if (!visible) failedGrabs.Clear();
        long now = Stopwatch.GetTimestamp();
        foreach (string key in new List<string>(grabbedKeys))
        {
            if (desired.Contains(key)) { deferredRelease.Remove(key); continue; }
            if (pressedKeys.Contains(key))
            {
                if (!deferredRelease.TryGetValue(key, out long deadline))
                {
                    deferredRelease[key] = now + Stopwatch.Frequency / 2;
                    continue;
                }
                if (now < deadline) continue;
            }
            UngrabKey(key);
        }
        foreach (string key in desired)
        {
            if (grabbedKeys.Contains(key)
                || (failedGrabs.TryGetValue(key, out int failures) && failures >= 3)) continue;
            try
            {
                byte result = ecore_wl2_window_keygrab_set(waylandWindow, key, 0, 0, 0, 2);
                Console.WriteLine("overlay_keygrab key={0} result={1} mode=topmost", key, result);
                if (result != 0) { grabbedKeys.Add(key); failedGrabs.Remove(key); }
                else failedGrabs[key] = failedGrabs.TryGetValue(key, out int count) ? count + 1 : 1;
            }
            catch (Exception error) when (error is EntryPointNotFoundException || error is DllNotFoundException)
            {
                Console.Error.WriteLine("overlay_keygrab unavailable: {0}", error.Message);
                inputReady = false;
                ReleaseAllKeyGrabs();
                break;
            }
        }
        Console.Out.Flush();
    }

    private static void UngrabKey(string key)
    {
        try
        {
            byte result = ecore_wl2_window_keygrab_unset(waylandWindow, key, 0, 0);
            Console.WriteLine("overlay_keyungrab key={0} result={1}", key, result);
        }
        catch (Exception error) when (error is EntryPointNotFoundException || error is DllNotFoundException)
        {
            Console.Error.WriteLine("overlay_keyungrab unavailable: {0}", error.Message);
        }
        grabbedKeys.Remove(key);
        pressedKeys.Remove(key);
        deferredRelease.Remove(key);
    }

    private static void ReleaseAllKeyGrabs()
    {
        foreach (string key in new List<string>(grabbedKeys)) UngrabKey(key);
        pressedKeys.Clear();
        deferredRelease.Clear();
    }

    private static void RemoveKeyInput()
    {
        if (keyDownHandler != IntPtr.Zero) { ecore_event_handler_del(keyDownHandler); keyDownHandler = IntPtr.Zero; }
        if (keyUpHandler != IntPtr.Zero) { ecore_event_handler_del(keyUpHandler); keyUpHandler = IntPtr.Zero; }
        if (inputLibrary != IntPtr.Zero) { NativeLibrary.Free(inputLibrary); inputLibrary = IntPtr.Zero; }
        inputReady = false;
    }

    private static string EventKeyName(IntPtr info)
    {
        // Ecore_Event_Key begins with const char *keyname on ARMv7 and 64-bit.
        return info == IntPtr.Zero ? null : Marshal.PtrToStringUTF8(Marshal.ReadIntPtr(info));
    }

    private static byte OnKeyDown(IntPtr data, int type, IntPtr info)
    {
        string key = EventKeyName(info);
        if (key == null || !grabbedKeys.Contains(key)) return 1;
        if (!pressedKeys.Add(key)) return 0;
        if (!visible) return 0;
        Console.WriteLine("overlay_key down={0}", key);
        try
        {
            if (key == "Return" || key == "KP_Enter")
            {
                if (!Interaction.IsExpanded && Interaction.Open())
                {
                    RenderCurrentScene();
                    SetVisible(true);
                    Console.WriteLine("overlay_details opened league={0}", Interaction.SelectedLeagueId);
                }
            }
            else if (Interaction.IsExpanded && (key == "XF86Back" || key == "Back" || key == "Escape"))
            {
                Interaction.Close();
                SetVisible(false);
                Console.WriteLine("overlay_details closed");
            }
            else if (Interaction.IsExpanded)
            {
                int direction = key == "Left" || key == "Up" ? -1 : key == "Right" || key == "Down" ? 1 : 0;
                if (Interaction.MoveLeague(direction))
                {
                    RenderCurrentScene();
                    SetVisible(true);
                    Console.WriteLine("overlay_details league={0}", Interaction.SelectedLeagueId);
                }
            }
        }
        catch (Exception error) when (IsStateError(error))
        {
            Interaction.Close();
            SetVisible(false);
            LogStateError(error.Message);
        }
        Console.Out.Flush();
        return 0;
    }

    private static byte OnKeyUp(IntPtr data, int type, IntPtr info)
    {
        string key = EventKeyName(info);
        if (key == null || !grabbedKeys.Contains(key)) return 1;
        pressedKeys.Remove(key);
        SynchronizeKeyGrabs();
        return 0;
    }

    private static void LogStateError(string message)
    {
        if (lastStateError == message) return;
        lastStateError = message;
        Console.Error.WriteLine("state_error: {0}", message);
    }

    private static int QuitMainLoop(IntPtr data)
    {
        RequestQuit("timer");
        return 0;
    }

    private static void OnCancelKeyPress(object sender, ConsoleCancelEventArgs args)
    {
        args.Cancel = true;
        RequestQuit("sigint");
    }

    private static void RequestQuit(string reason)
    {
        if (Interlocked.CompareExchange(ref quitRequested, 1, 0) != 0)
        {
            return;
        }

        quitReason = reason;
        if (Volatile.Read(ref mainLoopRunning) != 0)
        {
            ecore_main_loop_thread_safe_call_async(
                ThreadSafeQuitCallback,
                IntPtr.Zero);
        }
    }

    private static void QuitMainLoopFromSignal(IntPtr data)
    {
        ecore_main_loop_quit();
    }

    private static void ConfigureUiEnvironment()
    {
        Environment.SetEnvironmentVariable("HOME", "/opt/usr/home/owner");
        Environment.SetEnvironmentVariable("USER", "owner");
        Environment.SetEnvironmentVariable("LOGNAME", "owner");
        Environment.SetEnvironmentVariable("XDG_RUNTIME_DIR", "/run/user/5001");
        Environment.SetEnvironmentVariable("WAYLAND_DISPLAY", "wayland-0");
        Environment.SetEnvironmentVariable("ELM_PROFILE", "tv");
        Environment.SetEnvironmentVariable("ELM_DISPLAY", "wl");
        Environment.SetEnvironmentVariable("ELM_ENGINE", "wayland_shm");
        Environment.SetEnvironmentVariable("ECORE_EVAS_ENGINE", "wayland_shm");
        Environment.SetEnvironmentVariable("EVAS_WAYLAND_SHM_DISABLE_DMABUF", "1");
    }

    private sealed class NativeDiagnostics
    {
        private int savedStandardError;

        private NativeDiagnostics(int savedStandardError, string logPath)
        {
            this.savedStandardError = savedStandardError;
            LogPath = logPath;
        }

        internal string LogPath { get; }

        internal static NativeDiagnostics Start(bool verbose)
        {
            if (verbose)
            {
                return new NativeDiagnostics(-1, null);
            }

            Directory.CreateDirectory(Path.GetDirectoryName(DiagnosticLogPath));
            int saved = dup(StandardErrorFileDescriptor);
            if (saved < 0)
            {
                throw new IOException(
                    "dup(stderr) failed with errno "
                    + Marshal.GetLastWin32Error().ToString(CultureInfo.InvariantCulture));
            }

            int log = open(
                DiagnosticLogPath,
                OpenWriteOnly | OpenCreate | OpenTruncate,
                OwnerReadWriteGroupAndOtherRead);
            if (log < 0)
            {
                int error = Marshal.GetLastWin32Error();
                close(saved);
                throw new IOException(
                    "open(" + DiagnosticLogPath + ") failed with errno "
                    + error.ToString(CultureInfo.InvariantCulture));
            }

            if (dup2(log, StandardErrorFileDescriptor) < 0)
            {
                int error = Marshal.GetLastWin32Error();
                close(log);
                close(saved);
                throw new IOException(
                    "dup2(EFL log, stderr) failed with errno "
                    + error.ToString(CultureInfo.InvariantCulture));
            }
            close(log);
            return new NativeDiagnostics(saved, DiagnosticLogPath);
        }

        internal void Restore()
        {
            if (savedStandardError < 0)
            {
                return;
            }
            fflush(IntPtr.Zero);
            dup2(savedStandardError, StandardErrorFileDescriptor);
            close(savedStandardError);
            savedStandardError = -1;
        }
    }

    private sealed class SceneRenderer : IDisposable
    {
        private readonly IntPtr evas;
        private readonly List<IntPtr> retainedStyles = new List<IntPtr>();
        private readonly List<IntPtr> retainedObjects = new List<IntPtr>();
        private static bool fontSourceApiAvailable = true;
        private static bool fontMetricsApiAvailable = true;
        private const int MaximumFontDiagnostics = 16;
        private static readonly HashSet<string> warnedFontSources = new HashSet<string>(StringComparer.Ordinal);
        private static readonly HashSet<string> requestedFontFiles = new HashSet<string>(StringComparer.Ordinal);

        private static void WarnFontFallback(string path)
        {
            if (warnedFontSources.Add(path))
                Console.Error.WriteLine("font_source_unavailable source={0} fallback=named-font", JsonSerializer.Serialize(path));
        }
        internal int ObjectCount => retainedObjects.Count;

        internal void ShowAll()
        {
            foreach (IntPtr obj in retainedObjects) evas_object_show(obj);
        }

        public void Dispose()
        {
            foreach (IntPtr obj in retainedObjects) evas_object_del(obj);
            retainedObjects.Clear();
            foreach (IntPtr style in retainedStyles) evas_textblock_style_free(style);
            retainedStyles.Clear();
        }

        internal SceneRenderer(IntPtr evas)
        {
            this.evas = evas;
        }

        internal int RenderDefaultBanner(string message)
        {
            ShowRectangle(72, 72, 1180, 180, new Rgba(10, 10, 10, 224));
            ShowRectangle(72, 72, 14, 180, new Rgba(0, 190, 255, 255));
            ShowText(120, 128, message, "SamsungOne", 48, Rgba.White);
            return 3;
        }

        internal int RenderSceneFile(string path)
        {
            if (string.IsNullOrWhiteSpace(path))
            {
                throw new InvalidDataException("scene path is empty");
            }

            FileInfo scene = new FileInfo(path);
            if (!scene.Exists)
            {
                throw new FileNotFoundException("scene file does not exist", path);
            }
            if (scene.Length < 2 || scene.Length > MaximumSceneBytes)
            {
                throw new InvalidDataException(
                    "scene file must contain 2 through "
                    + MaximumSceneBytes.ToString(CultureInfo.InvariantCulture)
                    + " bytes");
            }

            JsonDocumentOptions options = new JsonDocumentOptions
            {
                AllowTrailingCommas = true,
                CommentHandling = JsonCommentHandling.Skip,
            };
            using (JsonDocument document = JsonDocument.Parse(File.ReadAllBytes(path), options))
            {
                return RenderScene(document.RootElement);
            }
        }

        internal int RenderScene(JsonElement root)
        {
            if (root.ValueKind != JsonValueKind.Object
                || !root.TryGetProperty("objects", out JsonElement objects)
                || objects.ValueKind != JsonValueKind.Array)
                throw new InvalidDataException("scene root must contain an objects array");
            int count = objects.GetArrayLength();
            if (count < 1 || count > MaximumSceneObjects)
                throw new InvalidDataException("scene objects must contain 1..256 entries");
            int index = 0;
            foreach (JsonElement item in objects.EnumerateArray())
            {
                try { RenderObject(item); }
                catch (InvalidDataException error)
                {
                    throw new InvalidDataException("objects[" + index.ToString(CultureInfo.InvariantCulture)
                        + "]: " + error.Message, error);
                }
                index++;
            }
            return count;
        }

        private void RenderObject(JsonElement item)
        {
            if (item.ValueKind != JsonValueKind.Object)
            {
                throw new InvalidDataException("object must be a JSON object");
            }

            string type = RequiredString(item, "type", 32).ToLowerInvariant();
            switch (type)
            {
                case "rectangle":
                    ShowRectangle(
                        Coordinate(item, "x"),
                        Coordinate(item, "y"),
                        Dimension(item, "width"),
                        Dimension(item, "height"),
                        Color(item, "color", Rgba.White));
                    return;
                case "gradient":
                    ShowGradient(ParseGradient(item));
                    return;
                case "ellipse":
                    ShowEllipse(
                        Coordinate(item, "x"),
                        Coordinate(item, "y"),
                        Dimension(item, "width"),
                        Dimension(item, "height"),
                        Color(item, "color", Rgba.White));
                    return;
                case "line":
                    ShowLine(
                        Coordinate(item, "x1"),
                        Coordinate(item, "y1"),
                        Coordinate(item, "x2"),
                        Coordinate(item, "y2"),
                        Color(item, "color", Rgba.White));
                    return;
                case "polygon":
                    ShowPolygon(item, Color(item, "color", Rgba.White));
                    return;
                case "image":
                    ShowImage(
                        Coordinate(item, "x"),
                        Coordinate(item, "y"),
                        Dimension(item, "width"),
                        Dimension(item, "height"),
                        RequiredString(item, "path", 4096),
                        OptionalBoolean(item, "smooth", true));
                    return;
                case "text":
                    ShowText(
                        Coordinate(item, "x"),
                        Coordinate(item, "y"),
                        RequiredString(item, "text", 16384),
                        Font(item),
                        FontSize(item),
                        Color(item, "color", Rgba.White),
                        OptionalInteger(item, "width", 0, 0, 8192),
                        OptionalInteger(item, "height", 0, 0, 8192),
                        ValidateFontSource(OptionalString(item, "fontSource", null, 4096)));
                    return;
                case "textblock":
                    ShowTextBlock(item);
                    return;
                case "subtitle":
                    ShowSubtitle(item);
                    return;
                default:
                    throw new InvalidDataException("unsupported object type " + type);
            }
        }

        private void ShowRectangle(int x, int y, int width, int height, Rgba color)
        {
            IntPtr obj = RequireObject(evas_object_rectangle_add(evas), "rectangle");
            ConfigureBox(obj, x, y, width, height, color);
        }

        private void ShowGradient(GradientParameters gradient)
        {
            IntPtr obj = RequireObject(evas_object_rectangle_add(evas), "gradient rectangle");
            // White source pixels let the map's premultiplied vertex colors define the fill.
            ConfigureBox(obj, gradient.X, gradient.Y, gradient.Width, gradient.Height, Rgba.White);
            IntPtr map = IntPtr.Zero;
            try
            {
                map = evas_map_new(4);
                if (map == IntPtr.Zero) throw new InvalidDataException("could not allocate gradient map");
                evas_map_util_points_populate_from_geometry(map,
                    gradient.X, gradient.Y, gradient.Width, gradient.Height, 0);
                for (int index = 0; index < 4; index++)
                {
                    int[] color = gradient.VertexColors[index];
                    evas_map_point_color_set(map, index, color[0], color[1], color[2], color[3]);
                }
                evas_map_alpha_set(map, 1);
                evas_map_smooth_set(map, 1);
                // Evas copies the map, so the temporary map can be freed immediately.
                evas_object_map_set(obj, map);
                evas_object_map_enable_set(obj, 1);
            }
            catch (Exception error) when (error is EntryPointNotFoundException || error is DllNotFoundException)
            {
                throw new InvalidDataException("native Evas gradient map API is unavailable", error);
            }
            finally
            {
                if (map != IntPtr.Zero) evas_map_free(map);
            }
            Show(obj);
        }

        private void ShowEllipse(int x, int y, int width, int height, Rgba color)
        {
            const int segments = 64;
            double centerX = x + (width / 2.0);
            double centerY = y + (height / 2.0);
            double radiusX = width / 2.0;
            double radiusY = height / 2.0;
            IntPtr obj = RequireObject(evas_object_polygon_add(evas), "ellipse polygon");
            for (int index = 0; index < segments; index++)
            {
                double angle = (Math.PI * 2.0 * index) / segments;
                evas_object_polygon_point_add(
                    obj,
                    (int)Math.Round(centerX + (Math.Cos(angle) * radiusX)),
                    (int)Math.Round(centerY + (Math.Sin(angle) * radiusY)));
            }
            ApplyColor(obj, color);
            Show(obj);
        }

        private void ShowLine(int x1, int y1, int x2, int y2, Rgba color)
        {
            IntPtr obj = RequireObject(evas_object_line_add(evas), "line");
            evas_object_line_xy_set(obj, x1, y1, x2, y2);
            ApplyColor(obj, color);
            Show(obj);
        }

        private void ShowPolygon(JsonElement item, Rgba color)
        {
            if (!item.TryGetProperty("points", out JsonElement points)
                || points.ValueKind != JsonValueKind.Array)
            {
                throw new InvalidDataException("polygon requires a points array");
            }
            int count = points.GetArrayLength();
            if (count < 3 || count > 128)
            {
                throw new InvalidDataException("polygon requires 3 through 128 points");
            }

            IntPtr obj = RequireObject(evas_object_polygon_add(evas), "polygon");
            foreach (JsonElement point in points.EnumerateArray())
            {
                if (point.ValueKind != JsonValueKind.Object)
                {
                    throw new InvalidDataException("polygon point must be an object");
                }
                evas_object_polygon_point_add(
                    obj,
                    Coordinate(point, "x"),
                    Coordinate(point, "y"));
            }
            ApplyColor(obj, color);
            Show(obj);
        }

        private void ShowImage(
            int x,
            int y,
            int width,
            int height,
            string path,
            bool smooth)
        {
            if (!Path.IsPathRooted(path))
            {
                throw new InvalidDataException("image path must be absolute");
            }
            if (!File.Exists(path))
            {
                throw new InvalidDataException("image file does not exist: " + path);
            }

            IntPtr obj = RequireObject(evas_object_image_add(evas), "image");
            // file_set returns void; reading its return register as an error
            // produces arbitrary failures. Query the documented error API.
            evas_object_image_file_set(obj, path, null);
            int loadError = evas_object_image_load_error_get(obj);
            if (loadError != 0)
            {
                throw new InvalidDataException(
                    "Evas could not load image " + path + " (error "
                    + loadError.ToString(CultureInfo.InvariantCulture) + ")");
            }
            evas_object_move(obj, x, y);
            evas_object_resize(obj, width, height);
            evas_object_image_fill_set(obj, 0, 0, width, height);
            // Evas's PNG loader handles alpha decoding/premultiplication. Keep
            // standard straight-alpha PNG assets unchanged, enable their alpha
            // channel, and use a neutral white object color (no extra tint).
            evas_object_image_alpha_set(obj, 1);
            evas_object_color_set(obj, 255, 255, 255, 255);
            evas_object_image_smooth_scale_set(obj, smooth ? (byte)1 : (byte)0);
            Show(obj);
        }

        private void ShowText(
            int x,
            int y,
            string value,
            string font,
            int size,
            Rgba color,
            int clipWidth = 0,
            int clipHeight = 0,
            string fontSource = null)
        {
            IntPtr obj = RequireObject(evas_object_text_add(evas), "text");
            TextFontSelection selected = SelectTextFont(font, fontSource,
                                                        fontSource != null && File.Exists(fontSource));
            if (selected.MissingSource) WarnFontFallback(fontSource);
            if (selected.Source != null)
            {
                if (fontSourceApiAvailable)
                {
                    try { evas_object_text_font_source_set(obj, selected.Source); }
                    catch (EntryPointNotFoundException)
                    {
                        fontSourceApiAvailable = false;
                        WarnFontFallback(selected.Source);
                    }
                }
                else WarnFontFallback(selected.Source);
            }
            // Full font-file paths are the documented Evas direct-file API.
            // No system Fontconfig registration or family/style guessing occurs.
            evas_object_text_font_set(obj, selected.Font, size);
            evas_object_text_text_set(obj, value);
            if (selected.DirectFile) ReportFontMetrics(obj, selected.Font, size, value.Length);
            ApplyColor(obj, color);
            evas_object_move(obj, x, y);
            if (clipWidth > 0)
            {
                IntPtr clipper = RequireObject(evas_object_rectangle_add(evas), "text clip rectangle");
                ConfigureBox(clipper, x, y, clipWidth, clipHeight > 0 ? clipHeight : size * 2, Rgba.White);
                evas_object_clip_set(obj, clipper);
            }
            Show(obj);
        }

        private void ReportFontMetrics(IntPtr text, string path, int size, int characterCount)
        {
            if (requestedFontFiles.Count >= MaximumFontDiagnostics || !requestedFontFiles.Add(path)) return;
            if (!fontMetricsApiAvailable)
            {
                Console.WriteLine("font_file_metrics file={0} api=evas_object_text_font_set size={1} result=metrics-api-unavailable",
                                  JsonSerializer.Serialize(path), size);
                return;
            }

            IntPtr probe = IntPtr.Zero;
            try
            {
                int advance = evas_object_text_horiz_advance_get(text);
                evas_object_geometry_get(text, out int x, out int y, out int width, out int height);
                // Fixed public digits/size make fonts comparable even when the
                // first real node has a different label or point size. This
                // object stays hidden and never enters the retained scene.
                const int probeSize = 64;
                probe = evas_object_text_add(evas);
                if (probe == IntPtr.Zero)
                {
                    Console.WriteLine("font_file_metrics file={0} size={1} character_count={2} advance={3} geometry_width={4} geometry_height={5} result=probe-unavailable",
                                      JsonSerializer.Serialize(path), size, characterCount, advance, width, height);
                    return;
                }
                evas_object_text_font_set(probe, path, probeSize);
                evas_object_text_text_set(probe, "0123456789");
                int probeAdvance = evas_object_text_horiz_advance_get(probe);
                evas_object_geometry_get(probe, out int probeX, out int probeY,
                                         out int probeWidth, out int probeHeight);
                Console.WriteLine("font_file_metrics file={0} api=evas_object_text_font_set size={1} character_count={2} advance={3} geometry_width={4} geometry_height={5} probe_size={6} probe_character_count=10 probe_advance={7} probe_geometry_width={8} probe_geometry_height={9} result=measured",
                                  JsonSerializer.Serialize(path), size, characterCount, advance, width, height,
                                  probeSize, probeAdvance, probeWidth, probeHeight);
            }
            catch (EntryPointNotFoundException)
            {
                fontMetricsApiAvailable = false;
                Console.WriteLine("font_file_metrics file={0} api=evas_object_text_font_set size={1} result=metrics-api-unavailable",
                                  JsonSerializer.Serialize(path), size);
            }
            finally
            {
                if (probe != IntPtr.Zero) evas_object_del(probe);
            }
        }

        private void ShowTextBlock(JsonElement item)
        {
            int x = Coordinate(item, "x");
            int y = Coordinate(item, "y");
            int width = Dimension(item, "width");
            int height = Dimension(item, "height");
            IntPtr obj = CreateTextBlock(item);
            evas_object_move(obj, x, y);
            evas_object_resize(obj, width, height);
            Show(obj);
        }

        private void ShowSubtitle(JsonElement item)
        {
            int x = OptionalInteger(item, "x", 190, -8192, 8192);
            int width = OptionalInteger(item, "width", 1540, 1, 8192);
            int bottom = OptionalInteger(item, "bottom", 1012, -8192, 8192);
            int horizontalPadding = OptionalInteger(item, "padding_x", 60, 0, 512);
            int verticalPadding = OptionalInteger(item, "padding_y", 24, 0, 512);
            if (width <= horizontalPadding * 2)
            {
                throw new InvalidDataException("subtitle width must exceed twice padding_x");
            }

            int contentWidth = width - (horizontalPadding * 2);
            IntPtr background = RequireObject(
                evas_object_rectangle_add(evas),
                "subtitle background");
            IntPtr text = CreateTextBlock(item);
            evas_object_resize(text, contentWidth, CanvasHeight);
            evas_object_textblock_size_formatted_get(
                text,
                out int formattedWidth,
                out int formattedHeight);
            if (formattedWidth < 1 || formattedHeight < 1 || formattedHeight > CanvasHeight)
            {
                throw new InvalidDataException(
                    "Evas returned invalid subtitle geometry "
                    + formattedWidth.ToString(CultureInfo.InvariantCulture) + "x"
                    + formattedHeight.ToString(CultureInfo.InvariantCulture));
            }

            // Evas' formatted height does not include every shadow/outline pixel.
            const int effectSafetyPixels = 12;
            int textHeight = formattedHeight + effectSafetyPixels;
            int outerHeight = textHeight + (verticalPadding * 2);
            int y = bottom - outerHeight;
            Rgba backgroundColor = Color(
                item,
                "background_color",
                new Rgba(0, 0, 0, 184));

            ConfigureBox(background, x, y, width, outerHeight, backgroundColor);
            evas_object_move(text, x + horizontalPadding, y + verticalPadding);
            evas_object_resize(text, contentWidth, textHeight);
            Show(text);
        }

        private IntPtr CreateTextBlock(JsonElement item)
        {
            string text = RequiredString(item, "text", 16384);
            string font = Font(item);
            int size = FontSize(item);
            Rgba color = Color(item, "color", Rgba.White);
            string align = Choice(item, "align", "center", "left", "center", "right");
            string valign = Choice(item, "valign", "center", "top", "center", "bottom");
            string wrap = Choice(item, "wrap", "word", "none", "word", "char", "mixed");
            string effect = Choice(
                item,
                "style",
                "outline_shadow",
                "plain",
                "shadow",
                "outline",
                "soft_outline",
                "outline_shadow",
                "far_shadow",
                "outline_soft_shadow");
            Rgba outlineColor = Color(item, "outline_color", Rgba.Black);
            Rgba shadowColor = Color(item, "shadow_color", new Rgba(0, 0, 0, 192));
            bool markup = OptionalBoolean(item, "markup", false);

            string styleValue = BuildTextBlockStyle(
                font,
                size,
                color,
                align,
                valign,
                wrap,
                effect,
                outlineColor,
                shadowColor);
            IntPtr style = evas_textblock_style_new();
            if (style == IntPtr.Zero || evas_textblock_style_set(style, styleValue) == 0)
            {
                throw new InvalidDataException("Evas rejected the textblock style");
            }
            retainedStyles.Add(style);

            IntPtr obj = RequireObject(evas_object_textblock_add(evas), "textblock");
            evas_object_textblock_style_set(obj, style);
            evas_object_textblock_text_markup_set(
                obj,
                markup ? text : EscapeTextBlockMarkup(text));
            return obj;
        }

        private static string BuildTextBlockStyle(
            string font,
            int size,
            Rgba color,
            string align,
            string valign,
            string wrap,
            string effect,
            Rgba outlineColor,
            Rgba shadowColor)
        {
            string effectProperties = effect == "plain"
                ? string.Empty
                : " style=" + effect
                    + " outline_color=" + outlineColor.ToEvasHex()
                    + " shadow_color=" + shadowColor.ToEvasHex();
            string vertical = valign == "top" ? "0.0" : valign == "bottom" ? "1.0" : "0.5";
            return "DEFAULT='font=" + font
                + " font_size=" + size.ToString(CultureInfo.InvariantCulture)
                + " color=" + color.ToEvasHex()
                + " align=" + align
                + " valign=" + vertical
                + " wrap=" + wrap
                + effectProperties
                + "'";
        }

        private static string EscapeTextBlockMarkup(string value)
        {
            StringBuilder escaped = new StringBuilder(value.Length + 32);
            foreach (char character in value)
            {
                switch (character)
                {
                    case '&':
                        escaped.Append("&amp;");
                        break;
                    case '<':
                        escaped.Append("&lt;");
                        break;
                    case '>':
                        escaped.Append("&gt;");
                        break;
                    case '\r':
                        break;
                    case '\n':
                        escaped.Append("<br/>");
                        break;
                    default:
                        escaped.Append(character);
                        break;
                }
            }
            return escaped.ToString();
        }

        private static string Font(JsonElement item)
        {
            string font = OptionalString(item, "font", "SamsungOne", 128);
            foreach (char character in font)
            {
                if (!char.IsLetterOrDigit(character)
                    && character != ' '
                    && character != '-'
                    && character != '_')
                {
                    throw new InvalidDataException("font contains an unsupported character");
                }
            }
            return font;
        }

        private static int FontSize(JsonElement item)
        {
            return OptionalInteger(item, "size", 48, 6, 300);
        }

        private static int Coordinate(JsonElement item, string name)
        {
            return RequiredInteger(item, name, -8192, 8192);
        }

        private static int Dimension(JsonElement item, string name)
        {
            return RequiredInteger(item, name, 1, 8192);
        }

        private static int RequiredInteger(
            JsonElement item,
            string name,
            int minimum,
            int maximum)
        {
            if (!item.TryGetProperty(name, out JsonElement property)
                || property.ValueKind != JsonValueKind.Number
                || !property.TryGetInt32(out int value)
                || value < minimum
                || value > maximum)
            {
                throw new InvalidDataException(
                    name + " must be an integer between "
                    + minimum.ToString(CultureInfo.InvariantCulture) + " and "
                    + maximum.ToString(CultureInfo.InvariantCulture));
            }
            return value;
        }

        private static int OptionalInteger(
            JsonElement item,
            string name,
            int defaultValue,
            int minimum,
            int maximum)
        {
            if (!item.TryGetProperty(name, out JsonElement property))
            {
                return defaultValue;
            }
            if (property.ValueKind != JsonValueKind.Number
                || !property.TryGetInt32(out int value)
                || value < minimum
                || value > maximum)
            {
                throw new InvalidDataException(
                    name + " must be an integer between "
                    + minimum.ToString(CultureInfo.InvariantCulture) + " and "
                    + maximum.ToString(CultureInfo.InvariantCulture));
            }
            return value;
        }

        private static string RequiredString(JsonElement item, string name, int maximumLength)
        {
            if (!item.TryGetProperty(name, out JsonElement property)
                || property.ValueKind != JsonValueKind.String)
            {
                throw new InvalidDataException(name + " must be a string");
            }
            string value = property.GetString() ?? string.Empty;
            if (value.Length < 1 || value.Length > maximumLength)
            {
                throw new InvalidDataException(
                    name + " must contain 1 through "
                    + maximumLength.ToString(CultureInfo.InvariantCulture)
                    + " characters");
            }
            return value;
        }

        private static string OptionalString(
            JsonElement item,
            string name,
            string defaultValue,
            int maximumLength)
        {
            if (!item.TryGetProperty(name, out JsonElement property))
            {
                return defaultValue;
            }
            if (property.ValueKind != JsonValueKind.String)
            {
                throw new InvalidDataException(name + " must be a string");
            }
            string value = property.GetString() ?? string.Empty;
            if (value.Length < 1 || value.Length > maximumLength)
            {
                throw new InvalidDataException(
                    name + " must contain 1 through "
                    + maximumLength.ToString(CultureInfo.InvariantCulture)
                    + " characters");
            }
            return value;
        }

        private static bool OptionalBoolean(JsonElement item, string name, bool defaultValue)
        {
            if (!item.TryGetProperty(name, out JsonElement property))
            {
                return defaultValue;
            }
            if (property.ValueKind != JsonValueKind.True
                && property.ValueKind != JsonValueKind.False)
            {
                throw new InvalidDataException(name + " must be a boolean");
            }
            return property.GetBoolean();
        }

        private static string Choice(
            JsonElement item,
            string name,
            string defaultValue,
            params string[] allowed)
        {
            string value = OptionalString(item, name, defaultValue, 64).ToLowerInvariant();
            foreach (string candidate in allowed)
            {
                if (value == candidate)
                {
                    return value;
                }
            }
            throw new InvalidDataException(
                name + " must be one of: " + string.Join(", ", allowed));
        }

        private static Rgba Color(JsonElement item, string name, Rgba defaultValue)
        {
            if (!item.TryGetProperty(name, out JsonElement property))
            {
                return defaultValue;
            }
            if (property.ValueKind != JsonValueKind.String)
            {
                throw new InvalidDataException(name + " must be a color string");
            }
            return Rgba.Parse(property.GetString() ?? string.Empty, name);
        }

        private void ConfigureBox(
            IntPtr obj,
            int x,
            int y,
            int width,
            int height,
            Rgba color)
        {
            evas_object_move(obj, x, y);
            evas_object_resize(obj, width, height);
            ApplyColor(obj, color);
            Show(obj);
        }

        private static void ApplyColor(IntPtr obj, Rgba color)
        {
            // Evas color_set consumes premultiplied RGB. Scene JSON remains straight RGBA.
            evas_object_color_set(obj,
                PremultiplyChannel(color.Red, color.Alpha),
                PremultiplyChannel(color.Green, color.Alpha),
                PremultiplyChannel(color.Blue, color.Alpha),
                color.Alpha);
        }

        private void Show(IntPtr obj)
        {
            // Keep staged objects hidden until the entire replacement scene validates.
            evas_object_pass_events_set(obj, 1);
        }

        private IntPtr RequireObject(IntPtr obj, string type)
        {
            if (obj == IntPtr.Zero)
            {
                throw new InvalidDataException("failed to create Evas " + type + " object");
            }
            retainedObjects.Add(obj);
            return obj;
        }
    }

    private readonly struct Rgba
    {
        internal static readonly Rgba White = new Rgba(255, 255, 255, 255);
        internal static readonly Rgba Black = new Rgba(0, 0, 0, 255);

        internal Rgba(int red, int green, int blue, int alpha)
        {
            Red = red;
            Green = green;
            Blue = blue;
            Alpha = alpha;
        }

        internal int Red { get; }
        internal int Green { get; }
        internal int Blue { get; }
        internal int Alpha { get; }

        internal static Rgba Parse(string value, string name)
        {
            if (value.Length != 7 && value.Length != 9 || value[0] != '#')
            {
                throw new InvalidDataException(
                    name + " must use #RRGGBB or #RRGGBBAA notation");
            }
            try
            {
                int red = int.Parse(value.Substring(1, 2), NumberStyles.HexNumber, CultureInfo.InvariantCulture);
                int green = int.Parse(value.Substring(3, 2), NumberStyles.HexNumber, CultureInfo.InvariantCulture);
                int blue = int.Parse(value.Substring(5, 2), NumberStyles.HexNumber, CultureInfo.InvariantCulture);
                int alpha = value.Length == 9
                    ? int.Parse(value.Substring(7, 2), NumberStyles.HexNumber, CultureInfo.InvariantCulture)
                    : 255;
                return new Rgba(red, green, blue, alpha);
            }
            catch (FormatException error)
            {
                throw new InvalidDataException(
                    name + " must use hexadecimal #RRGGBB or #RRGGBBAA notation",
                    error);
            }
        }

        internal string ToEvasHex()
        {
            return "#"
                + Red.ToString("x2", CultureInfo.InvariantCulture)
                + Green.ToString("x2", CultureInfo.InvariantCulture)
                + Blue.ToString("x2", CultureInfo.InvariantCulture)
                + Alpha.ToString("x2", CultureInfo.InvariantCulture);
        }
    }
}
