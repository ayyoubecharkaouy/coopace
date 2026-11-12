package recovery

func ReasonLabel(code string) string {
	labels := map[string]string{
		"incomplete_snapshot":                     "La capture contient des lectures indisponibles.",
		"single_noqueue_root_required":            "Une seule racine noqueue avec handle 0: est requise.",
		"empty_noqueue_options_required":          "Les options noqueue doivent être présentes et vides.",
		"invalid_qdisc_counter":                   "Un compteur de file est invalide.",
		"unsupported_qdisc_field":                 "La file comporte un champ ou une dépendance non pris en charge.",
		"classes_or_filters_present":              "Des classes ou filtres sont présents ; leur restauration reste à développer.",
		"link_qdisc_inconsistent":                 "La file du lien et la lecture des qdisc ne concordent pas.",
		"link_identity_incomplete":                "L'adresse matérielle du lien doit correspondre à l'identité relevée.",
		"noqueue_without_visible_dependencies":    "Racine noqueue sans classes ni filtres dans les sélections observées.",
		"baseline_not_supported":                  "La référence initiale n'est pas prise en charge.",
		"later_distinct_observation_required":     "Une observation distincte, postérieure à la référence, est requise.",
		"interface_identity_or_state_changed":     "L'identité, le MTU ou les flags de l'interface ont changé.",
		"incomplete_after_snapshot":               "La capture après intervention est partielle.",
		"after_state_outside_baseline_profile":    "L'état observé après intervention diffère du profil initial.",
		"noqueue_and_selected_dependencies_match": "La racine noqueue et les dépendances sélectionnées correspondent à l'état initial.",
		"distinct_snapshot_files_required":        "La même capture ne peut pas prouver un retour à l'état initial.",
	}
	if label := labels[code]; label != "" {
		return label
	}
	return code
}

func StepLabel(code string) string {
	labels := map[string]string{
		"capture_and_compare_initial_state":          "Relire l'état initial et confirmer sa correspondance avec la référence.",
		"record_owned_root_installation":             "Consigner durablement l'installation de la file possédée par Coopace.",
		"recheck_namespace_link_and_owned_root":      "Vérifier à nouveau l'espace réseau, le lien et la file possédée.",
		"remove_only_owned_root":                     "Retirer uniquement cette file sous supervision indépendante.",
		"capture_and_compare_selected_initial_state": "Recapturer et comparer l'état sélectionné à la référence initiale.",
	}
	if label := labels[code]; label != "" {
		return label
	}
	return code
}
