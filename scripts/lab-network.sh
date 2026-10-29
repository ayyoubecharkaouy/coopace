#!/bin/sh
# Disposable IPv4 test topology. No host interface, route, firewall or qdisc edits.
set -eu

lab_mode=${1:-plan}
if [ "$#" -gt 1 ]; then
    printf '%s\n' 'Utilisation : sh scripts/lab-network.sh [plan|run|run-tcp|run-load]' >&2
    exit 2
fi
case "$lab_mode" in
    plan)
        printf '%s\n' \
            'Laboratoire prévu : client -> passerelle -> serveur, dans trois espaces réseau Linux neufs.' \
            'Client 10.203.0.2/30 -> passerelle lan 10.203.0.1/30' \
            'Passerelle wan 10.203.0.5/30 -> serveur 10.203.0.6/30' \
            'Routes spécifiques seulement ; aucun accès Internet ni lien avec le réseau de l’hôte.' \
            'run vérifie le blocage sans forwarding, puis trois réponses ICMP avec forwarding.' \
            'run-tcp ajoute cinq tentatives TCP vers 10.203.0.6:46001, sans charge générée.' \
            'run-load transfère 8 Mio synthétiques vers 10.203.0.6:46002, plafonnés à 1 Mio/s en moyenne applicative.' \
            'stdout : inventaire JSON de la passerelle ; stderr : étapes, sondes et nettoyage.' \
            'Avec run-tcp, stdout contient plutôt le rapport TCP local JSON de l’agent.' \
            'Avec run-load, stdout contient le rapport JSON d’envoi après réception complète et nettoyage.' \
            'Nettoyage des seuls espaces créés après succès, erreur ou interruption gérée.' \
            'Prérequis de run : Linux, binaire coopace-gateway construit, privilèges de laboratoire.' \
            'run-tcp exige plutôt les binaires coopace et coopace-lab-tcp déjà construits.' \
            'run-load exige le binaire coopace-lab-load ; ce flux ne prouve pas une saturation.' \
            'Ce mode plan ne crée aucun espace réseau et ne lance aucune sonde.'
        exit 0
        ;;
    run|run-tcp|run-load) ;;
    *)
        printf '%s\n' 'Utilisation : sh scripts/lab-network.sh [plan|run|run-tcp|run-load]' >&2
        exit 2
        ;;
esac

for lab_command in uname id sed ip ping sysctl mktemp rmdir rm sleep; do
    if ! command -v "$lab_command" >/dev/null 2>&1; then
        printf 'Outil requis absent : %s\n' "$lab_command" >&2
        exit 1
    fi
done
if [ "$(uname -s)" != Linux ]; then
    printf '%s\n' 'Le laboratoire virtuel est disponible sous Linux uniquement.' >&2
    exit 1
fi
if [ "$(id -u)" != 0 ]; then
    printf '%s\n' 'run exige les privilèges de laboratoire ; consulter docs/VIRTUAL_LAB.md.' >&2
    exit 1
fi
lab_caps=$(sed -n 's/^CapEff:[[:space:]]*//p' /proc/self/status)
case "$lab_caps" in
    ''|*[!0-9a-fA-F]*)
        printf '%s\n' 'Impossible de vérifier les capacités effectives du processus.' >&2
        exit 1
        ;;
esac
lab_required=$(( (1 << 12) | (1 << 13) | (1 << 21) ))
if [ $(( 0x$lab_caps & lab_required )) -ne "$lab_required" ]; then
    printf '%s\n' 'run requiert CAP_NET_ADMIN, CAP_NET_RAW et CAP_SYS_ADMIN ; aucun espace créé.' >&2
    exit 1
fi
lab_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
if [ "$lab_mode" = run ]; then
    lab_binary="$lab_root/.local/bin/coopace-gateway"
    if [ ! -x "$lab_binary" ]; then
        printf '%s\n' 'Compiler coopace-gateway avec le compte habituel avant de lancer run.' >&2
        exit 1
    fi
elif [ "$lab_mode" = run-tcp ]; then
    lab_agent="$lab_root/.local/bin/coopace"
    lab_tcp="$lab_root/.local/bin/coopace-lab-tcp"
    if [ ! -x "$lab_agent" ] || [ ! -x "$lab_tcp" ]; then
        printf '%s\n' 'Compiler coopace et coopace-lab-tcp avant run-tcp ; consulter docs/VIRTUAL_LAB.md.' >&2
        exit 1
    fi
else
    lab_load="$lab_root/.local/bin/coopace-lab-load"
    if [ ! -x "$lab_load" ]; then
        printf '%s\n' 'Compiler coopace-lab-load avant run-load ; consulter docs/VIRTUAL_LOAD.md.' >&2
        exit 1
    fi
fi

# The private reservation supplies a random run ID, not shell code or state.
lab_tmp=$(mktemp -d /tmp/coopace-lab.XXXXXXXX)
lab_tag=${lab_tmp##*/}
lab_token=${lab_tag#coopace-lab.}
case "$lab_token" in
    ''|*[!a-zA-Z0-9]*) rmdir -- "$lab_tmp"; exit 1 ;;
esac
if [ "${#lab_token}" -ne 8 ]; then
    rmdir -- "$lab_tmp"
    exit 1
fi
lab_client="cp-$lab_token-c"
lab_gateway="cp-$lab_token-g"
lab_server="cp-$lab_token-s"
lab_client_created=0
lab_gateway_created=0
lab_server_created=0
lab_report=''
lab_server_pid=''
lab_ready_file=''
lab_critical=0
lab_signal_status=0

# Defer managed interrupts until a newly created resource has been recorded.
# Otherwise a successful ip command can be followed by a trap before its flag.
lab_signal() {
    if [ "$lab_signal_status" = 0 ]; then lab_signal_status=$1; fi
    if [ "$lab_critical" = 0 ]; then
        exit "$lab_signal_status"
    fi
}

lab_end_critical() {
    lab_critical=0
    if [ "$lab_signal_status" -ne 0 ]; then
        exit "$lab_signal_status"
    fi
}

lab_wait_ready() {
    lab_ready_attempt=0
    while :; do
        if IFS= read -r lab_ready < "$lab_ready_file" && [ "$lab_ready" = "$1" ]; then
            return 0
        fi
        if ! kill -0 "$lab_server_pid" 2>/dev/null || [ "$lab_ready_attempt" -ge 50 ]; then
            printf '%s\n' 'Serveur de laboratoire indisponible ; essai arrêté.' >&2
            return 1
        fi
        lab_ready_attempt=$((lab_ready_attempt + 1))
        sleep 0.1
    done
}

lab_cleanup() {
    lab_result=$?
    if [ "$lab_signal_status" -ne 0 ]; then lab_result=$lab_signal_status; fi
    trap - EXIT
    trap '' HUP INT TERM
    lab_cleanup_failed=0
    # Stop and reap our child before deleting its namespace. No broad PID search.
    if [ -n "$lab_server_pid" ]; then
        kill "$lab_server_pid" 2>/dev/null || :
        wait "$lab_server_pid" 2>/dev/null || :
        lab_server_pid=''
    fi
    if [ -n "$lab_ready_file" ]; then
        rm -f -- "$lab_ready_file" || lab_cleanup_failed=1
    fi
    if [ "$lab_server_created" = 1 ]; then
        ip netns del "$lab_server" >&2 || lab_cleanup_failed=1
    fi
    if [ "$lab_client_created" = 1 ]; then
        ip netns del "$lab_client" >&2 || lab_cleanup_failed=1
    fi
    if [ "$lab_gateway_created" = 1 ]; then
        ip netns del "$lab_gateway" >&2 || lab_cleanup_failed=1
    fi
    rmdir -- "$lab_tmp" || lab_cleanup_failed=1
    if [ "$lab_cleanup_failed" = 1 ]; then
        printf 'Nettoyage incomplet. Inspecter ces noms uniquement : %s %s %s\n' \
            "$lab_client" "$lab_gateway" "$lab_server" >&2
        if [ "$lab_result" = 0 ]; then lab_result=1; fi
    else
        printf '%s\n' 'Ressources créées par cette exécution supprimées.' >&2
    fi
    if [ "$lab_result" = 0 ]; then
        printf '%s\n' "$lab_report"
    fi
    exit "$lab_result"
}
trap lab_cleanup EXIT
trap 'lab_signal 129' HUP
trap 'lab_signal 130' INT
trap 'lab_signal 143' TERM

printf 'Espaces de cette exécution : %s %s %s\n' \
    "$lab_client" "$lab_gateway" "$lab_server" >&2
printf 'Réservation temporaire : %s\n' "$lab_tmp" >&2
lab_critical=1
ip netns add "$lab_client"
lab_client_created=1
lab_end_critical
lab_critical=1
ip netns add "$lab_gateway"
lab_gateway_created=1
lab_end_critical
lab_critical=1
ip netns add "$lab_server"
lab_server_created=1
lab_end_critical

for lab_namespace in "$lab_client" "$lab_gateway" "$lab_server"; do
    ip -n "$lab_namespace" link set lo up
done
# Both veth pairs originate in the fresh gateway namespace, never in the host.
ip -n "$lab_gateway" link add lan type veth peer name eth0 netns "$lab_client"
ip -n "$lab_gateway" link add wan type veth peer name eth0 netns "$lab_server"
ip -n "$lab_client" address add 10.203.0.2/30 dev eth0
ip -n "$lab_gateway" address add 10.203.0.1/30 dev lan
ip -n "$lab_gateway" address add 10.203.0.5/30 dev wan
ip -n "$lab_server" address add 10.203.0.6/30 dev eth0
ip -n "$lab_client" link set eth0 up
ip -n "$lab_gateway" link set lan up
ip -n "$lab_gateway" link set wan up
ip -n "$lab_server" link set eth0 up
ip -n "$lab_client" route add 10.203.0.4/30 via 10.203.0.1
ip -n "$lab_server" route add 10.203.0.0/30 via 10.203.0.5

ip netns exec "$lab_gateway" sysctl -q -w net.ipv4.ip_forward=0
printf '%s\n' 'Vérification du blocage IPv4 sans forwarding...' >&2
if ip netns exec "$lab_client" ping -4 -n -c 1 -w 3 -W 1 10.203.0.6 >&2; then
    printf '%s\n' 'Passage inattendu sans forwarding ; essai arrêté.' >&2
    exit 1
else
    lab_ping_result=$?
    if [ "$lab_ping_result" != 1 ]; then
        printf 'La sonde a échoué techniquement (code %s) ; résultat non interprétable.\n' "$lab_ping_result" >&2
        exit 1
    fi
fi
ip netns exec "$lab_gateway" sysctl -q -w net.ipv4.ip_forward=1
printf '%s\n' 'Vérification du passage IPv4 par la passerelle...' >&2
ip netns exec "$lab_client" ping -4 -n -c 3 -w 5 -W 1 10.203.0.6 >&2
if [ "$lab_mode" = run ]; then
    printf '%s\n' 'Test de passage réussi ; collecte de l’inventaire du laboratoire.' >&2
    lab_report=$(ip netns exec "$lab_gateway" "$lab_binary" inspect --json)
else
    if [ "$lab_mode" = run-tcp ]; then
        lab_ready_file="$lab_tmp/tcp-ready"
    else
        lab_ready_file="$lab_tmp/load-ready"
    fi
    : > "$lab_ready_file"
    lab_critical=1
    if [ "$lab_mode" = run-tcp ]; then
        ip netns exec "$lab_server" "$lab_tcp" --listen 10.203.0.6:46001 \
            --connections 5 --duration 15s > "$lab_ready_file" &
    else
        ip netns exec "$lab_server" "$lab_load" receive --listen 10.203.0.6:46002 \
            --bytes 8388608 --duration 15s > "$lab_ready_file" &
    fi
    lab_server_pid=$!
    lab_end_critical
    printf 'Serveur de cette exécution : PID %s\n' "$lab_server_pid" >&2
    if [ "$lab_mode" = run-tcp ]; then
        lab_wait_ready 'READY 10.203.0.6:46001'
        printf '%s\n' 'Mesure de cinq établissements TCP dans le laboratoire, sans charge ajoutée.' >&2
        lab_report=$(ip netns exec "$lab_client" "$lab_agent" latency \
            --target 10.203.0.6:46001 --count 5 --timeout 1s --interval 250ms \
            --condition unspecified --json)
    else
        lab_wait_ready 'READY 10.203.0.6:46002'
        printf '%s\n' 'Envoi de 8388608 octets synthétiques, plafonné à 1048576 octets/s en moyenne applicative.' >&2
        lab_report=$(ip netns exec "$lab_client" "$lab_load" send --target 10.203.0.6:46002 \
            --bytes 8388608 --rate 1048576 --duration 12s)
    fi
    if wait "$lab_server_pid"; then
        lab_server_pid=''
    else
        lab_server_pid=''
        printf '%s\n' 'Le serveur de laboratoire n’a pas terminé le travail attendu.' >&2
        exit 1
    fi
fi
if [ -z "$lab_report" ]; then
    printf '%s\n' 'Rapport vide ; essai arrêté.' >&2
    exit 1
fi
