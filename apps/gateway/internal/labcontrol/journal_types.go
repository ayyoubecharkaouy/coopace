package labcontrol

import "github.com/ayyoubecharkaouy/coopace/apps/gateway/internal/buildinfo"

type journalToolSpec struct {
	Path   string `json:"path"`
	SHA256 string `json:"sha256"`
}

type journalNamespace struct {
	Device uint64 `json:"device"`
	Inode  uint64 `json:"inode"`
}

type journalBuildInfo struct {
	GoVersion string `json:"go_version"`
	VCS       string `json:"vcs"`
	Revision  string `json:"vcs_revision"`
	Modified  *bool  `json:"vcs_modified"`
}

func journalBuild() journalBuildInfo {
	info := buildinfo.Local()
	return journalBuildInfo{info.GoVersion, info.VCS, info.Revision, info.Modified}
}
