#include "../firmware/main/voice_cancel_io.cpp"
#include <arpa/inet.h>
#include <array>
#include <cassert>
#include <cstdio>
#include <thread>
#include <vector>

std::array<int,2> connection() {
    const int listener=::socket(AF_INET,SOCK_STREAM,0);
    assert(listener>=0);
    sockaddr_in address{};
    address.sin_family=AF_INET; address.sin_addr.s_addr=htonl(INADDR_LOOPBACK);
    assert(::bind(listener,reinterpret_cast<sockaddr*>(&address),sizeof(address))==0);
    assert(::listen(listener,1)==0);
    socklen_t length=sizeof(address);
    assert(::getsockname(listener,reinterpret_cast<sockaddr*>(&address),&length)==0);
    const int client=::socket(AF_INET,SOCK_STREAM,0);
    voice_cancel_begin();
    assert(voice_cancel_connect(client,reinterpret_cast<sockaddr*>(&address),sizeof(address))==0);
    const int peer=::accept(listener,nullptr,nullptr);
    assert(peer>=0);
    ::close(listener);
    return {client,peer};
}
void finish(std::array<int,2> pair) {
    voice_cancel_close(pair[0]); ::close(pair[1]); voice_cancel_finish();
    assert(g_voice_cancel_socket.load()==-1);
}
int main() {
    auto pair=connection();
    voice_io_timeout(1000);
    assert(voice_cancel_send(pair[0],"abc",3,0)==3);
    char data[3]{};
    assert(::recv(pair[1],data,3,MSG_WAITALL)==3);
    assert(data[0]=='a' && data[2]=='c');
    assert(::send(pair[1],"ok",2,0)==2);
    assert(voice_cancel_recv(pair[0],data,2,0)==2 && data[0]=='o');
    voice_io_timeout(80);
    uint64_t started=voice_io_now_ms();
    assert(voice_cancel_recv(pair[0],data,1,0)<0 && errno==ETIMEDOUT);
    assert(voice_io_now_ms()-started>=70 && voice_io_now_ms()-started<1500);
    finish(pair);

    pair=connection();
    std::thread trickle([peer=pair[1]] {
        for(int i=0;i<8;++i) { std::this_thread::sleep_for(std::chrono::milliseconds(30)); ::send(peer,"x",1,0); }
    });
    voice_io_timeout(120); started=voice_io_now_ms();
    int received=0;
    while(voice_cancel_recv(pair[0],data,1,0)>0) ++received;
    assert(errno==ETIMEDOUT && received>0 && received<8);
    assert(voice_io_now_ms()-started<1500); // Incoming trickles cannot reset the budget.
    trickle.join(); finish(pair);

    pair=connection();
    std::thread cancel([] { std::this_thread::sleep_for(std::chrono::milliseconds(25)); voice_cancel_request(); });
    voice_io_timeout(10000); started=voice_io_now_ms();
    assert(voice_cancel_recv(pair[0],data,1,0)<=0);
    cancel.join();
    assert(voice_cancel_is_requested() && voice_io_now_ms()-started<1500);
    finish(pair);

    pair=connection();
    int small=1024;
    assert(::setsockopt(pair[0],SOL_SOCKET,SO_SNDBUF,&small,sizeof(small))==0);
    std::vector<char> large(4*1024*1024,'x');
    voice_io_timeout(100); started=voice_io_now_ms();
    size_t sent=0;
    while(sent<large.size()) {
        int n=voice_cancel_send(pair[0],large.data()+sent,large.size()-sent,0);
        if(n<=0) break;
        sent+=n;
    }
    assert(sent<large.size() && errno==ETIMEDOUT);
    assert(voice_io_now_ms()-started<1500);
    finish(pair);
    std::puts("VOICE_SOCKET PASS real_tcp=1 receive_deadline=1 trickle_deadline=1 send_deadline=1 cancel=1 next_connection=1");
}
