param(
  [int]$ListenPort = 8099,
  [string]$ListenAddress = "127.0.0.1",
  [Parameter(Mandatory=$true)][string]$TargetAddress,
  [Parameter(Mandatory=$true)][int]$TargetPort,
  [ValidateSet("add","remove","show")] [string]$Action = "add"
)

if ($Action -eq "show") {
  netsh interface portproxy show v4tov4
}
elseif ($Action -eq "remove") {
  netsh interface portproxy delete v4tov4 listenaddress=$ListenAddress listenport=$ListenPort
}
elseif ($Action -eq "add") {
  netsh interface portproxy add v4tov4 listenaddress=$ListenAddress listenport=$ListenPort connectaddress=$TargetAddress connectport=$TargetPort
}
