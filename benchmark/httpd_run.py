import tempfile
import subprocess
import sys
import pathlib
import signal


bin_httpd = pathlib.Path(sys.argv[1])
bin_hey = pathlib.Path(sys.argv[2])
modules_root = pathlib.Path(sys.argv[3])
port = int(sys.argv[4])
n_requests = int(sys.argv[5])


# See https://superuser.com/a/1079037
httpd_conf = '''
ServerRoot $HTTPD_ROOT
PidFile $HTTPD_ROOT/httpd.pid
ErrorLog $HTTPD_ROOT/errors.log
ServerName localhost
Listen $PORT
LoadModule mpm_event_module $MODULES_ROOT/mod_mpm_event.so
LoadModule unixd_module $MODULES_ROOT/mod_unixd.so
LoadModule authz_core_module $MODULES_ROOT/mod_authz_core.so
DocumentRoot $SRV_ROOT
'''


with tempfile.TemporaryDirectory() as _httpd_root:
    httpd_root = pathlib.Path(_httpd_root)
    srv_root = httpd_root / "srv"
    srv_root.mkdir()
    (srv_root / "test.html").write_text("<h1>Hello world 1234!</h1>")
    conf_file = httpd_root / "httpd.conf"
    conf_file.write_text(
        pathlib.Path("httpd.conf").read_text()
        .replace("$HTTPD_ROOT", str(httpd_root))
        .replace("$MODULES_ROOT", str(modules_root))
        .replace("$SRV_ROOT", str(srv_root))
        .replace("$PORT", str(port))
    )
    httpd_proc = subprocess.Popen(
        [bin_httpd, "-k", "start", "-f", conf_file],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    hey_proc = subprocess.run(
        [bin_hey, "-n", str(n_requests), f"localhost:{port}/test.html"],
        check=True,
        capture_output=True,
    )
    httpd_proc.send_signal(signal.SIGTERM)
