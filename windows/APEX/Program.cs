using System.Runtime.InteropServices;
using Microsoft.UI.Dispatching;
using Microsoft.UI.Xaml;
using Microsoft.Windows.Widgets.Providers;
using WinRT;

namespace Apex;

public static class Program
{
    /// One exe, two roles: the Widgets Board launches it with -RegisterProcessAsComServer; the Start menu opens the companion window.
    [MTAThread]
    public static void Main(string[] args)
    {
        ComWrappersSupport.InitializeComWrappers();
        if (args.Contains("-RegisterProcessAsComServer"))
        {
            var clsid = typeof(WidgetProvider).GUID;
            Marshal.ThrowExceptionForHR(CoRegisterClassObject(clsid, new ProviderFactory(), CLSCTX_LOCAL_SERVER, REGCLS_MULTIPLEUSE, out var cookie));
            WidgetProvider.Empty.Wait();  // exit once the last widget is removed
            CoRevokeClassObject(cookie);
            return;
        }
        if (args is ["-DumpCards", var dir, ..])
        {
            // Debug: write the exact (template, data) the board would get, for every widget and size.
            var loaded = Api.Snapshot(args.ElementAtOrDefault(2)).GetAwaiter().GetResult();
            Directory.CreateDirectory(dir);
            foreach (var kind in Enum.GetValues<Kind>())
                foreach (var size in new[] { "small", "medium", "large" })
                {
                    var (template, data) = Cards.Build(kind, size, loaded, new WidgetSettings(args.ElementAtOrDefault(2)), DateTimeOffset.Now);
                    File.WriteAllText(Path.Combine(dir, $"{kind}-{size}.json"),
                        $"{{\"template\":{Cards.Template(template)},\"data\":{data}}}");
                }
            return;
        }
        if (args.Contains("-Desktop"))
        {
            // Desktop widgets: one host per user session; later launches just exit (the host watches desktop.json).
            using var single = new Mutex(true, @"Local\APEX.DesktopWidgets", out var first);
            if (first) RunUi(() => new DesktopApp());
            return;
        }
        RunUi(() => new App());
    }

    /// WinUI needs an STA thread; Main stays MTA for the COM server path.
    static void RunUi(Func<Application> create)
    {
        var ui = new Thread(() => Application.Start(p =>
        {
            SynchronizationContext.SetSynchronizationContext(new DispatcherQueueSynchronizationContext(DispatcherQueue.GetForCurrentThread()));
            _ = create();
        }));
        ui.SetApartmentState(ApartmentState.STA);
        ui.Start();
        ui.Join();
    }

    const uint CLSCTX_LOCAL_SERVER = 0x4, REGCLS_MULTIPLEUSE = 1;
    const int CLASS_E_NOAGGREGATION = unchecked((int)0x80040110), E_NOINTERFACE = unchecked((int)0x80004002);
    static readonly Guid IID_IUnknown = new("00000000-0000-0000-C000-000000000046");

    [DllImport("ole32.dll")]
    static extern int CoRegisterClassObject([MarshalAs(UnmanagedType.LPStruct)] Guid rclsid, [MarshalAs(UnmanagedType.IUnknown)] object pUnk,
        uint dwClsContext, uint flags, out uint lpdwRegister);

    [DllImport("ole32.dll")]
    static extern int CoRevokeClassObject(uint dwRegister);

    [ComImport, ComVisible(false), InterfaceType(ComInterfaceType.InterfaceIsIUnknown), Guid("00000001-0000-0000-C000-000000000046")]
    interface IClassFactory
    {
        [PreserveSig] int CreateInstance(IntPtr pUnkOuter, ref Guid riid, out IntPtr ppvObject);
        [PreserveSig] int LockServer(bool fLock);
    }

    sealed class ProviderFactory : IClassFactory
    {
        public int CreateInstance(IntPtr pUnkOuter, ref Guid riid, out IntPtr ppvObject)
        {
            ppvObject = IntPtr.Zero;
            if (pUnkOuter != IntPtr.Zero) return CLASS_E_NOAGGREGATION;
            if (riid != typeof(WidgetProvider).GUID && riid != IID_IUnknown) return E_NOINTERFACE;
            ppvObject = MarshalInspectable<IWidgetProvider>.FromManaged(new WidgetProvider());
            return 0;
        }

        public int LockServer(bool fLock) => 0;
    }
}
