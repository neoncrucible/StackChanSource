#include <atomic>
#include <cerrno>
#include <cstddef>
#include <cstdint>
#include <algorithm>
#include <fcntl.h>

#ifdef ESP_PLATFORM
#include "lwip/sockets.h"
#include "esp_timer.h"
#else
#include <chrono>
#include <sys/socket.h>
#include <sys/select.h>
#include <unistd.h>
#endif

namespace {

std::atomic<bool> g_voice_cancel_requested{false};
std::atomic<int> g_voice_cancel_socket{-1};
uint64_t g_voice_io_deadline_ms = 0; // Owned exclusively by the media worker.

uint64_t voice_io_now_ms()
{
#ifdef ESP_PLATFORM
    return static_cast<uint64_t>(esp_timer_get_time()) / 1000;
#else
    return std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count();
#endif
}

void voice_io_timeout(uint32_t milliseconds)
{
    g_voice_io_deadline_ms = voice_io_now_ms() + milliseconds;
}

void voice_cancel_begin()
{
    g_voice_cancel_requested.store(false);
    g_voice_cancel_socket.store(-1);
    voice_io_timeout(10000);
}

bool voice_cancel_is_requested()
{
    return g_voice_cancel_requested.load();
}

void voice_cancel_request()
{
    g_voice_cancel_requested.store(true);
    const int sock = g_voice_cancel_socket.load();
    if (sock >= 0) {
        (void)::shutdown(sock, SHUT_RDWR);
    }
}

bool voice_io_ready(int sock, bool writing)
{
    for (;;) {
        if (voice_cancel_is_requested()) { errno=ECANCELED; return false; }
        const uint64_t now=voice_io_now_ms();
        if (now >= g_voice_io_deadline_ms) { errno=ETIMEDOUT; return false; }
        fd_set ready;
        FD_ZERO(&ready);
        FD_SET(sock,&ready);
        timeval interval{};
        interval.tv_usec=static_cast<long>(std::min<uint64_t>(100,g_voice_io_deadline_ms-now)*1000);
        const int result=::select(sock+1,writing?nullptr:&ready,writing?&ready:nullptr,nullptr,&interval);
        if (result>0) return true;
        if (result<0 && errno!=EINTR) return false;
    }
}

int voice_cancel_connect(int sock, const struct sockaddr* address, socklen_t address_len)
{
    if (voice_cancel_is_requested()) {
        errno = ECANCELED;
        return -1;
    }
    g_voice_cancel_socket.store(sock);
    voice_io_timeout(10000);
    const int flags=::fcntl(sock,F_GETFL,0);
    if (flags<0 || ::fcntl(sock,F_SETFL,flags|O_NONBLOCK)<0) return -1;
    int result = ::connect(sock, address, address_len);
    if (result<0 && errno==EINPROGRESS && voice_io_ready(sock,true)) {
        int error=0;
        socklen_t size=sizeof(error);
        result=::getsockopt(sock,SOL_SOCKET,SO_ERROR,&error,&size);
        if (result==0 && error!=0) { errno=error; result=-1; }
    }
    if (result != 0) {
        int expected = sock;
        (void)g_voice_cancel_socket.compare_exchange_strong(expected, -1);
    }
    return result;
}

int voice_cancel_send(int sock, const void* data, std::size_t length, int flags)
{
    while (voice_io_ready(sock,true)) {
        const int result=static_cast<int>(::send(sock,data,length,flags));
        if (result>=0 || (errno!=EAGAIN && errno!=EWOULDBLOCK && errno!=EINTR)) return result;
    }
    return -1;
}

int voice_cancel_recv(int sock, void* data, std::size_t length, int flags)
{
    while (voice_io_ready(sock,false)) {
        const int result=static_cast<int>(::recv(sock,data,length,flags));
        if (result>=0 || (errno!=EAGAIN && errno!=EWOULDBLOCK && errno!=EINTR)) return result;
    }
    return -1;
}

int voice_cancel_close(int sock)
{
    int expected = sock;
    (void)g_voice_cancel_socket.compare_exchange_strong(expected, -1);
    return ::close(sock);
}

void voice_cancel_finish()
{
    g_voice_cancel_socket.store(-1);
}

}  // namespace
