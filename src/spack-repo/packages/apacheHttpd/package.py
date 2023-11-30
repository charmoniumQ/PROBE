# Copyright 2013-2023 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)

from spack.package import *


class Apachehttpd(AutotoolsPackage):
    """Apache HTTPD, the world's most popular web server"""

    homepage = "https://httpd.apache.org"
    url = "https://dlcdn.apache.org/httpd/httpd-2.4.58.tar.bz2"

    maintainers("charmoniumQ")

    license("asl20")

    version("2.4.58", sha256="fa16d72a078210a54c47dd5bef2f8b9b8a01d94909a51453956b3ec6442ea4c5")

    variant("proxy", default=True, description="Whether to enable proxy support")
    variant("brotli", default=True, description="Whether to enable brotli support")
    variant("ssl", default=True, description="Whether to enable SSL support")
    variant("ldap", default=True, description="Whether to enable LDAP integration")
    variant("libxml2", default=True, description="Whether to enable libxml2 support")
    variant("http2", default=True, description="Whether to enable HTTP2 support")
    variant("lua", default=True, description="Whether to enable Lua interpreter")

    # Based on https://github.com/NixOS/nixpkgs/blob/19e27c3547b51e8705855879a4f55846c75ee5fb/pkgs/servers/http/apache-httpd/2.4.nix
    depends_on("apr")
    depends_on("apr-util")
    depends_on("zlib")
    depends_on("pcre2")
    depends_on("perl")
    depends_on("libxcrypt")
    depends_on("brotli", when="+brotli")
    depends_on("openssl", when="+ssl")
    depends_on("openldap", when="+ldap")
    depends_on("libxml2", when="+libxml2")
    depends_on("nghttp2", when="+http2")
    depends_on("lua", when="+lua")

    def configure_args(self):
        enable_feature = lambda name: (
            "--enable-%s" % name
            if self.spec.satisfies("+%s" % name) else
            "--disable-%s" % name
        )
        with_feature_as = lambda name: (
            "--with-%s=%s" % (name, self.spec[name].prefix)
            if self.spec.satisfies("+%s" % name) else
            "--without-%s" % name
        )

        # Based on https://github.com/NixOS/nixpkgs/blob/19e27c3547b51e8705855879a4f55846c75ee5fb/pkgs/servers/http/apache-httpd/2.4.nix
        args = [
            f"--with-apr=%s" % self.spec["apr"].prefix,
            f"--with-apr-util=%s" % self.spec["apr-util"].prefix,
            f"--with-z=%s" % self.spec["zlib"].prefix,
            f"--with-pcre=%s/bin/pcre2-config" % self.spec["pcre2"].prefix,
            "--disable-maintainer-mode",
            "--disable-debugger-mode",
            "--enable-mods--shared=all",
            "--enable-mpms-shared=all",
            "--enable-cern-meta",
            "--enable-imagemap",
            "--enable-cgi",
            enable_feature("proxy"),
            enable_feature("ssl"),
            "--disable-tls",
            (
                "--with-libxml2=%s/include/libxml2" % self.spec["libxml2"].prefix
                if self.spec.satisfies("+libxml2") else
                "--without-libxml2"
            ),

            enable_feature("brotli"),
            with_feature_as("brotli"),

            enable_feature("http2"),
            (
                "--with-nghttp2=%s" % self.spec["nghttp2"].prefix
                if self.spec.satisfies("+http2") else
                "--without-nghttp2"
            ),

            enable_feature("lua"),
            with_feature_as("lua"),
        ]
        print(args)
        return args
