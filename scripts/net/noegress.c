/* noegress: LD_PRELOAD egress gate for cutoff-restricted Rethlas runs.
 *
 * Policy: loopback is always allowed; hostnames matching RETHLAS_NET_ALLOW
 * (comma-separated substrings) are allowed (the model's own API endpoint and
 * the frozen proxy host -- we sandbox the model's *retrieval*, not its brain
 * or its inference endpoint); everything else is blocked.
 *
 * getaddrinfo refuses non-allowed hostnames (stops curl/wget/python before
 * they connect), and for allowed hostnames records the resolved IPs so
 * connect() can permit them. connect() independently blocks any non-loopback,
 * non-recorded IP (stops direct-IP connects). The frozen proxy runs WITHOUT
 * this preload and is reached over 127.0.0.1.
 */
#define _GNU_SOURCE
#include <netdb.h>
#include <string.h>
#include <stdlib.h>
#include <dlfcn.h>
#include <pthread.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <errno.h>

static int (*real_gai)(const char*,const char*,const struct addrinfo*,struct addrinfo**);
static int (*real_connect)(int,const struct sockaddr*,socklen_t);

#define MAX_OK 512
static unsigned char ok4[MAX_OK][4];
static unsigned char ok6[MAX_OK][16];
static int n_ok4 = 0, n_ok6 = 0;
static pthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER;

static int host_allowed(const char *node){
  if(!node) return 0;
  if(strcmp(node,"127.0.0.1")==0||strcmp(node,"localhost")==0||strcmp(node,"::1")==0) return 1;
  const char *allow = getenv("RETHLAS_NET_ALLOW");
  if(!allow || !*allow) return 0;
  char buf[1024]; strncpy(buf,allow,sizeof buf-1); buf[sizeof buf-1]=0;
  for(char *tok=strtok(buf,","); tok; tok=strtok(NULL,",")){
    while(*tok==' ') tok++;
    if(*tok && strstr(node,tok)) return 1;
  }
  return 0;
}

static void record(struct addrinfo *res){
  pthread_mutex_lock(&lock);
  for(struct addrinfo *p=res; p; p=p->ai_next){
    if(p->ai_family==AF_INET && n_ok4<MAX_OK)
      memcpy(ok4[n_ok4++], &((struct sockaddr_in*)p->ai_addr)->sin_addr, 4);
    else if(p->ai_family==AF_INET6 && n_ok6<MAX_OK)
      memcpy(ok6[n_ok6++], &((struct sockaddr_in6*)p->ai_addr)->sin6_addr, 16);
  }
  pthread_mutex_unlock(&lock);
}

int getaddrinfo(const char *node,const char *service,const struct addrinfo *hints,struct addrinfo **res){
  if(!real_gai) real_gai=dlsym(RTLD_NEXT,"getaddrinfo");
  if(!host_allowed(node)) return EAI_FAIL;
  int rc = real_gai(node,service,hints,res);
  if(rc==0 && res && *res) record(*res);
  return rc;
}

int connect(int fd,const struct sockaddr *addr,socklen_t len){
  if(!real_connect) real_connect=dlsym(RTLD_NEXT,"connect");
  if(addr){
    if(addr->sa_family==AF_INET){
      unsigned char *ip=(unsigned char*)&((struct sockaddr_in*)addr)->sin_addr;
      if(ip[0]==127) goto allow;
      pthread_mutex_lock(&lock);
      for(int i=0;i<n_ok4;i++) if(memcmp(ok4[i],ip,4)==0){ pthread_mutex_unlock(&lock); goto allow; }
      pthread_mutex_unlock(&lock);
      errno=ECONNREFUSED; return -1;
    } else if(addr->sa_family==AF_INET6){
      struct in6_addr *a6=&((struct sockaddr_in6*)addr)->sin6_addr;
      if(IN6_IS_ADDR_LOOPBACK(a6)) goto allow;
      pthread_mutex_lock(&lock);
      for(int i=0;i<n_ok6;i++) if(memcmp(ok6[i],a6,16)==0){ pthread_mutex_unlock(&lock); goto allow; }
      pthread_mutex_unlock(&lock);
      errno=ECONNREFUSED; return -1;
    }
  }
allow:
  return real_connect(fd,addr,len);
}
