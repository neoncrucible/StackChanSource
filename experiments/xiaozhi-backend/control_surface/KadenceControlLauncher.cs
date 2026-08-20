using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Windows.Forms;

namespace KadenceControlSurface
{
    internal static class Program
    {
        [STAThread]
        private static void Main()
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);

            try
            {
                string script = FindLauncherScript();
                if (script == null)
                {
                    MessageBox.Show(
                        "Could not find start_control_surface.ps1.\r\n\r\n" +
                        "Keep this EXE inside the Project-Kadence-2.0 tree, set KADENCE_HOME, " +
                        "or rebuild it after moving the project.",
                        "Kadence Control Surface",
                        MessageBoxButtons.OK,
                        MessageBoxIcon.Error);
                    return;
                }

                string system32 = Environment.GetFolderPath(Environment.SpecialFolder.System);
                string powershell = Path.Combine(system32, "WindowsPowerShell", "v1.0", "powershell.exe");
                if (!File.Exists(powershell))
                {
                    MessageBox.Show(
                        "Windows PowerShell 5.1 was not found:\r\n" + powershell,
                        "Kadence Control Surface",
                        MessageBoxButtons.OK,
                        MessageBoxIcon.Error);
                    return;
                }

                var psi = new ProcessStartInfo
                {
                    FileName = powershell,
                    Arguments = "-STA -NoLogo -NoProfile -ExecutionPolicy Bypass -File \"" + script + "\"",
                    WorkingDirectory = Path.GetDirectoryName(script),
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    WindowStyle = ProcessWindowStyle.Hidden
                };

                using (var process = Process.Start(psi))
                {
                    if (process == null)
                    {
                        throw new InvalidOperationException("Windows failed to start the Kadence Control Surface host.");
                    }
                    process.WaitForExit();
                    if (process.ExitCode != 0)
                    {
                        MessageBox.Show(
                            "Kadence Control Surface exited with code " + process.ExitCode + ".",
                            "Kadence Control Surface",
                            MessageBoxButtons.OK,
                            MessageBoxIcon.Error);
                    }
                }
            }
            catch (Exception ex)
            {
                MessageBox.Show(
                    ex.Message,
                    "Kadence Control Surface",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error);
            }
        }

        private static string FindLauncherScript()
        {
            string envHome = Environment.GetEnvironmentVariable("KADENCE_HOME");
            if (!string.IsNullOrWhiteSpace(envHome))
            {
                string found = Probe(envHome);
                if (found != null) return found;
            }

            string exeDir = Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location);
            string foundFromExe = ProbeAncestors(exeDir);
            if (foundFromExe != null) return foundFromExe;

            string foundFromCwd = ProbeAncestors(Environment.CurrentDirectory);
            if (foundFromCwd != null) return foundFromCwd;

            string knownProject = @"C:\AI Project\Project-Kadence-2.0";
            string known = Probe(knownProject);
            if (known != null) return known;

            return null;
        }

        private static string ProbeAncestors(string start)
        {
            if (string.IsNullOrWhiteSpace(start)) return null;
            DirectoryInfo current;
            try { current = new DirectoryInfo(start); }
            catch { return null; }

            for (int i = 0; i < 8 && current != null; i++, current = current.Parent)
            {
                string found = Probe(current.FullName);
                if (found != null) return found;
            }
            return null;
        }

        private static string Probe(string root)
        {
            if (string.IsNullOrWhiteSpace(root)) return null;

            string direct = Path.Combine(root, "start_control_surface.ps1");
            if (File.Exists(direct)) return Path.GetFullPath(direct);

            string nested = Path.Combine(root, "experiments", "xiaozhi-backend", "start_control_surface.ps1");
            if (File.Exists(nested)) return Path.GetFullPath(nested);

            return null;
        }
    }
}
