param([string]$Uri='https://raw.githubusercontent.com/gnutls/gnutls/3.7.9/lib/crypto-selftests-pk.c')
$ErrorActionPreference='Stop'
# Public upstream source only. Never print or persist its key material.
$s=(Invoke-WebRequest -Uri $Uri).Content
$sha=[Security.Cryptography.SHA256]::Create()
function Hash([byte[]]$b) { [Convert]::ToHexString($sha.ComputeHash($b)).ToLower() }
$rows=@()
$r=[regex]::Matches($s,'static const char\s+(\w+)\[\]\s*=\s*((?:\s*"(?:[^"\\]|\\.)*")+)\s*;')
foreach($m in $r){
  $v=''
  foreach($q in [regex]::Matches($m.Groups[2].Value,'"((?:[^"\\]|\\.)*)"')){
    $v += $q.Groups[1].Value.Replace('\n',"`n").Replace('\r',"`r")
  }
  if($v.StartsWith('-----BEGIN ')){
    $b64=([regex]::Replace($v,'-----[^\r\n]*?-----','') -replace '\s','')
    $rows += [pscustomobject]@{
      symbol=$m.Groups[1].Value
      length=[Text.Encoding]::ASCII.GetByteCount($v)
      newline_after_begin=[regex]::IsMatch($v,'^-----BEGIN [^-]+-----\r?\n')
      newline_before_end=[regex]::IsMatch($v,'\r?\n-----END [^-]+-----')
      pem_sha256=Hash ([Text.Encoding]::ASCII.GetBytes($v))
      pem_no_terminal_newline_sha256=Hash ([Text.Encoding]::ASCII.GetBytes($v.TrimEnd([char[]]"`r`n")))
      der_sha256=Hash ([Convert]::FromBase64String($b64))
    }
  }
}
[pscustomobject]@{source_url=$Uri;source_utf8_sha256=Hash ([Text.Encoding]::UTF8.GetBytes($s));keys=$rows} | ConvertTo-Json -Depth 4
