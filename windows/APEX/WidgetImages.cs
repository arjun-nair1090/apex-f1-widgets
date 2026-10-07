using System.Runtime.InteropServices;
using Microsoft.UI.Dispatching;
using Microsoft.Web.WebView2.Core;
using Windows.Storage.Streams;

namespace Apex;

/// Pictures of the real widgets (desktop.html, the same page the desktop widgets show) for the Widgets board and the
/// lock screen, so they look exactly like the desktop ones. One offscreen WebView2 on its own thread loads the page at
/// the board's tile size and photographs it. Returns null on any failure; callers fall back to their text cards.
public static class WidgetImages
{
    // Board tile sizes (Adaptive Cards designer, "Widgets Board" host) and the web layout that fits each one.
    static readonly Dictionary<string, (int W, int H, string Layout)> Tiles = new()
    {
        ["small"] = (300, 146, "s"), ["medium"] = (300, 304, "m"), ["large"] = (300, 462, "l"),
    };
    const int HeaderInset = 48;  // the board draws the widget's icon, name and menu over the top 48 px
    const double Scale = 2;      // stays sharp on high-DPI screens
    static readonly TimeSpan Timeout = TimeSpan.FromSeconds(20);

    static readonly SemaphoreSlim Gate = new(1, 1);  // one page at a time
    static DispatcherQueueController? thread;
    // Held for the renderer's lifetime: if the .NET wrappers were collected, their event subscriptions would go with
    // them and WebView2 would call back into freed handlers (lost "ready" messages, then a crash).
    static CoreWebView2Environment? environment;
    static CoreWebView2Controller? controller;
    static CoreWebView2? web;
    static TaskCompletionSource<string>? page;      // "ready" or "failed", posted by desktop.html
    static int capture;                             // tags each capture's URL: events from earlier pages are ignored
    static ulong navigation;                        // the current capture's navigation

    public static string WebId(Kind kind) => kind switch
    {
        Kind.Favourite => "fav", Kind.Circuit => "track", _ => kind.ToString().ToLowerInvariant(),
    };

    /// data: URI of the widget as a PNG, or null.
    public static async Task<string?> Render(Kind kind, string size, WidgetSettings cfg)
    {
        if (!Tiles.TryGetValue(size, out var tile)) return null;
        var url = $"{Api.BaseUrl}/desktop.html?w={WebId(kind)}&s={tile.Layout}&density={Uri.EscapeDataString(cfg.Density)}" +
                  $"&capture={HeaderInset}" + (cfg.Driver is null ? "" : $"&driver={Uri.EscapeDataString(cfg.Driver)}");
        await Gate.WaitAsync();
        try
        {
            var png = await OnThread(() => Capture(url, tile.W, tile.H));
            return png is null ? null : "data:image/png;base64," + Convert.ToBase64String(png);
        }
        catch (Exception) { return null; }  // no WebView2 runtime, page error, render thread gone
        finally { Gate.Release(); }
    }

    /// Runs `work` on the render thread, where WebView2 must be created and called.
    static Task<T> OnThread<T>(Func<Task<T>> work)
    {
        thread ??= DispatcherQueueController.CreateOnDedicatedThread();
        var queue = thread.DispatcherQueue;
        var done = new TaskCompletionSource<T>(TaskCreationOptions.RunContinuationsAsynchronously);
        if (!queue.TryEnqueue(async () =>
            {
                SynchronizationContext.SetSynchronizationContext(new DispatcherQueueSynchronizationContext(queue));
                try { done.SetResult(await work()); }
                catch (Exception e) { done.SetException(e); }
            }))
            done.SetException(new InvalidOperationException("render thread is gone"));
        return done.Task;
    }

    /// Continue on the render thread. Awaits don't reliably resume there on their own (WebView2 calls from any
    /// other thread fail), so the code hops back explicitly after each wait.
    static Task Back()
    {
        var back = new TaskCompletionSource();  // completes on the render thread, so the await continues there
        if (!thread!.DispatcherQueue.TryEnqueue(() => back.SetResult())) back.SetException(new InvalidOperationException("render thread is gone"));
        return back.Task;
    }

    static async Task<byte[]?> Capture(string url, int width, int height)
    {
        if (controller is null) await CreateController();
        var (c, w) = (controller!, web!);
        await Back();
        c.Bounds = new Windows.Foundation.Rect(0, 0, width * Scale, height * Scale);
        page = new(TaskCreationOptions.RunContinuationsAsynchronously);
        navigation = 0;
        w.Navigate($"{url}&n={++capture}");
        var ok = await Task.WhenAny(page.Task, Task.Delay(Timeout)) == page.Task && page.Task.Result == "ready";
        await Back();
        if (!ok)
        {
            w.Navigate("about:blank");  // don't leave a hung page running
            return null;
        }
        using var stream = new InMemoryRandomAccessStream();
        await w.CapturePreviewAsync(CoreWebView2CapturePreviewImageFormat.Png, stream);  // streams are thread-agile
        using var reader = new DataReader(stream.GetInputStreamAt(0));
        await reader.LoadAsync((uint)stream.Size);
        var png = new byte[stream.Size];
        reader.ReadBytes(png);
        return png;
    }

    static async Task CreateController()
    {
        // Its own profile: the desktop widgets' WebView2 runs with different browser arguments, and two environments
        // with different arguments can't share one user data folder.
        var folder = Path.Combine(Windows.Storage.ApplicationData.Current.LocalFolder.Path, "EBWebView-cards");
        var options = new CoreWebView2EnvironmentOptions
        {
            // The window is off-screen; keep Chromium painting it anyway.
            AdditionalBrowserArguments = "--disable-features=CalculateNativeWinOcclusion --disable-backgrounding-occluded-windows --disable-renderer-backgrounding",
        };
        var env = environment = await CoreWebView2Environment.CreateWithOptionsAsync("", folder, options);
        await Back();
        var c = await env.CreateCoreWebView2ControllerAsync(CoreWebView2ControllerWindowReference.CreateFromWindowHandle((ulong)CreateHostWindow()));
        await Back();
        c.ShouldDetectMonitorScaleChanges = false;
        c.BoundsMode = CoreWebView2BoundsMode.UseRawPixels;
        c.RasterizationScale = Scale;
        c.DefaultBackgroundColor = Windows.UI.Color.FromArgb(255, 0x15, 0x15, 0x1E);  // carbon, as the desktop widgets
        c.IsVisible = true;
        var w = c.CoreWebView2;
        var s = w.Settings;
        s.AreDefaultContextMenusEnabled = s.AreDevToolsEnabled = s.IsStatusBarEnabled = false;
        // Starting the next capture can cancel the previous page's navigation, and a slow page can still post: only
        // events from the current capture's page count.
        bool Current(string uri) => uri.EndsWith($"&n={capture}", StringComparison.Ordinal);
        w.NavigationStarting += (_, e) => { if (Current(e.Uri)) navigation = e.NavigationId; };
        w.NavigationCompleted += (_, e) => { if (e.NavigationId == navigation && !e.IsSuccess) page?.TrySetResult("failed"); };
        w.WebMessageReceived += (_, e) => { if (Current(e.Source)) page?.TrySetResult(e.TryGetWebMessageAsString()); };
        (controller, web) = (c, w);
    }

    /// WebView2 needs a parent window: a tool window (no taskbar button) parked far off-screen, never activated.
    static IntPtr CreateHostWindow()
    {
        const uint WS_POPUP = 0x80000000, WS_VISIBLE = 0x10000000, WS_EX_TOOLWINDOW = 0x80, WS_EX_NOACTIVATE = 0x08000000;
        var hwnd = CreateWindowEx(WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE, "STATIC", "APEX widget renderer", WS_POPUP | WS_VISIBLE,
            -32000, -32000, 1200, 1200, IntPtr.Zero, IntPtr.Zero, IntPtr.Zero, IntPtr.Zero);
        return hwnd != IntPtr.Zero ? hwnd : throw new InvalidOperationException("no host window");
    }

    [DllImport("user32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    static extern IntPtr CreateWindowEx(uint exStyle, string className, string title, uint style, int x, int y, int w, int h,
        IntPtr parent, IntPtr menu, IntPtr instance, IntPtr param);
}
