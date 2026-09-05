#include <atomic>
#include <cerrno>
#include <cstddef>

#include "lwip/sockets.h"

namespace {

std::atomic<bool> g_voice_cancel_requested{false};
std::atomic<int> g_voice_cancel_socket{-1};

void voice_cancel_begin()
{
    g_voice_cancel_requested.store(false);
    g_voice_cancel_socket.store(-1);
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

int voice_cancel_connect(int sock, const struct sockaddr* address, socklen_t address_len)
{
    if (voice_cancel_is_requested()) {
        errno = ECANCELED;
        return -1;
    }
    g_voice_cancel_socket.store(sock);
    const int result = ::connect(sock, address, address_len);
    if (result != 0) {
        int expected = sock;
        (void)g_voice_cancel_socket.compare_exchange_strong(expected, -1);
    }
    return result;
}

int voice_cancel_send(int sock, const void* data, std::size_t length, int flags)
{
    if (voice_cancel_is_requested()) {
        errno = ECANCELED;
        return -1;
    }
    return static_cast<int>(::send(sock, data, length, flags));
}

int voice_cancel_recv(int sock, void* data, std::size_t length, int flags)
{
    if (voice_cancel_is_requested()) {
        errno = ECANCELED;
        return -1;
    }
    return static_cast<int>(::recv(sock, data, length, flags));
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
