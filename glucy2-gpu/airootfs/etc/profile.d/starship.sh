# Enable starship prompt with the system-wide config (interactive bash only)
[ -n "$BASH_VERSION" ] || return 0
case $- in *i*) ;; *) return 0 ;; esac
command -v starship >/dev/null 2>&1 || return 0
export STARSHIP_CONFIG=/etc/starship.toml
eval "$(starship init bash)"
