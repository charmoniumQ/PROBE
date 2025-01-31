#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/types.h>
#include <unistd.h>
#include <fcntl.h>

int
main(void)
{
    pid_t pid;

    if (signal(SIGCHLD, SIG_IGN) == SIG_ERR) {
             perror("signal");
             exit(EXIT_FAILURE);
         }
         pid = fork();
         switch (pid) {
             case -1:
                 perror("fork");
                 exit(EXIT_FAILURE);
             case 0:
                 execl(realpath("./test0", NULL), "test0", NULL);
                 exit(EXIT_SUCCESS);
             default:
                 creat("test2.txt", 0644);
                 int status;
                 waitpid(pid, &status, 0);
                 printf("Child exit status: %d\n", status);
                 exit(EXIT_SUCCESS);
         }
}
