#include <sys/stat.h>
#include <string_view>
#include <iomanip>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <x86intrin.h>
#include <arpa/inet.h>
#include <cstring>
#include <sys/socket.h>
#include <unistd.h>
#include <cpuid.h>
#include <immintrin.h>

const unsigned int width = 20;

std::hash<std::string> hasher;

std::ostream& print_field(std::ostream& os, const std::string& field) {
    return os << std::left << std::setw(20) << (field + ": ");
}

std::ostream& print_hex(std::ostream& os, std::int64_t hash) {
    return os << std::setw(16) << std::setfill('0') << std::hex << hash << std::setfill(' ');
}

// https://stackoverflow.com/a/40903508/1078199
auto read_file(const std::string& path) -> std::string {
    // Open the stream to 'lock' the file.
    std::ifstream f(path, std::ios::in | std::ios::binary);

    // Obtain the size of the file.
    const auto sz = std::filesystem::file_size(path);

    // Create a buffer.
    std::string result(sz, '\0');

    // Read the whole file into the buffer.
    f.read(result.data(), sz);

    return result;
}

void env(std::ostream& os) {
    print_field(os, "env") << std::getenv("test_env_var") << std::endl;
}

void fs_contents(std::ostream& os) {
    std::string result = read_file("test_files/contents");
    print_field(os, "FS contents") << result << std::endl;
}

void dir_order(std::ostream& os) {
    unsigned long result = 0;
    const std::filesystem::path dir {"test_files/disorderfs"};
    unsigned long i = 0;
    for (const auto& dir_entry : std::filesystem::directory_iterator{dir}) {
        result ^= hasher(dir_entry.path().filename()) << i;
        i++;
    }
    print_field(os, "dir order") << result << std::endl;
}

void inode(std::ostream& os) {
    struct stat statbuf;
    int ret = ::stat("test_files/inode", &statbuf);
    if (ret == -1) {
        perror("stat test_files/inode:");
    }
    print_field(os, "inodes?") << statbuf.st_ino << std::endl;
}

void time(std::ostream& os) {
    const auto p1 = std::chrono::system_clock::now();
    auto thousand = 1000;
    print_field(os, "time") << std::chrono::duration_cast<std::chrono::nanoseconds>(p1.time_since_epoch()).count() % (thousand * thousand * thousand) << '\n';
}

void proc(std::ostream& os) {
    std::filesystem::path proc_self {"/proc/self"};
    std::string result = std::filesystem::read_symlink(proc_self).filename();
    print_field(os, "/proc?") << result << std::endl;
}

void sys(std::ostream& os) {
    print_hex(print_field(os, "/sys?"), hasher(read_file("/sys/devices/system/node/node0/meminfo"))) << std::endl;
}

void dev_random(std::ostream& os) {
    std::ifstream f {"/dev/urandom", std::ios_base::in | std::ios_base::binary};
    const long size = 128;
    char buffer[size];
    f.read(buffer, size);
    print_hex(print_field(os, "/deva/u?random?"), hasher(std::string{buffer, size})) << std::endl;
}

void aslr(std::ostream& os) {
    print_field(os, "/aslr?") << malloc(10) << std::endl;
}

void umask(std::ostream& os) {
    std::filesystem::path test {"test_files/umask_test_file"};
    if (std::filesystem::exists(test)) {
        std::filesystem::remove(test);
    }
    std::ofstream file {test, std::ios_base::out};
    file << "hi";
    file.close();
    auto perms = std::filesystem::status(test).permissions();
    auto r = std::filesystem::perms::none == (perms & std::filesystem::perms::others_read);
    auto w = std::filesystem::perms::none == (perms & std::filesystem::perms::others_write);
    auto x = std::filesystem::perms::none == (perms & std::filesystem::perms::others_exec);
    print_field(os, "umask") << r << w << x << std::endl;
}

void net(std::ostream& os) {
    const char* addr = "1.1.1.1";
    int socket_fd = socket(PF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (socket_fd == -1) {
        perror("cannot create socket");
        return;
    }

    struct sockaddr_in sa;
    memset(&sa, 0, sizeof sa);

    sa.sin_family = AF_INET;
    sa.sin_port = htons(80);
    int res = inet_pton(AF_INET, addr, &sa.sin_addr);
    if (res != 1) {
        std::cerr << "inet_pton failed";
        return;
    }

    if (connect(socket_fd, (struct sockaddr *)&sa, sizeof sa) == -1) {
        perror("connect failed");
        close(socket_fd);
        return;
    }

    const char req[] = "GET / HTTP/1.1\r\nHost: 1.1.1.1\r\n\r\n";
    write(socket_fd, req, sizeof(req));

    constexpr int resp_size = 4096;
    char resp[resp_size];
    read(socket_fd, resp, resp_size);

    print_hex(print_field(os, "net"), hasher(std::string{resp, resp_size})) << std::endl;
}

void rdtsc(std::ostream& os) {
    print_field(os, "rdtsc") << __rdtsc() << std::endl;
}

void rdrand(std::ostream& os) {
    unsigned long long result = 0ULL;
    int rc = _rdrand64_step(&result);
    if (rc != 1) {
        return;
    }
    print_field(os, "rdrand") << result << std::endl;
}

int main() {
    auto& os = std::cout;
    os << "Note tests ending with '?' _may_ succeed even if the underlying resource is not fixed." << std::endl;
    env(os);
    fs_contents(os);
    dir_order(os);
    inode(os);
    time(os);
    dev_random(os);
    proc(os);
    sys(os);
    umask(os);
    aslr(os);
    net(os);
    rdtsc(os);
    rdrand(os);

    return 0;
}
