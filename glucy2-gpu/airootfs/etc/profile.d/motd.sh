# Live ISO login banner (static /etc/motd cannot run fastfetch)
case $- in *i*) ;; *) return 0 ;; esac

printf '\n  Login:  user \033[1mlive\033[0m  /  password \033[1mlive\033[0m\n\n'
command -v fastfetch >/dev/null 2>&1 &&
  fastfetch --logo arch_small \
    --structure OS:Host:Kernel:Display:CPU:GPU:Memory:Disk:LocalIp:Battery
printf '\n'
