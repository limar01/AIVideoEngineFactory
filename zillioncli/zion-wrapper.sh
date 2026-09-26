#!/bin/bash
# zion — Arena AI CLI (via live browser session)
set -e
case $1 in
  send|s)      shift; exec python3 $HOME/.local/bin/zion-send $@ ;;
  ls|l)        shift; exec python3 $HOME/.local/bin/zion-ls $@ ;;
  open|o)      shift; exec python3 $HOME/.local/bin/zion-open $@ ;;
  status)      exec python3 $HOME/.local/bin/zion-status ;;
  *) echo 'zion <send|ls|open|status>  [args]' ; echo '  send "msg"      -> magpadala ng mensahe at i-echo ang AI reply' ; echo '  ls [limit]      -> listahan ng chat history' ; echo '  open <sid>      -> ipakita ang transcript ng isang session' ; echo '  status          -> kalusugan ng probe browser + login' ;;
esac
