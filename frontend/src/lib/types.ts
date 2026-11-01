export type Role = 'viewer' | 'member' | 'admin';
export type Permission = 'view' | 'edit' | 'camera_control' | 'admin';

export interface Person {
	id: number;
	name: string;
	color: string;
}

export interface Me extends Person {
	email: string;
	role: Role;
	active: boolean;
	has_password: boolean;
	has_google: boolean;
	mute_until: string | null;
	notify_bookings: boolean;
	notify_radio: boolean;
	created_at: string;
	last_seen_at: string | null;
	can: Record<Permission, boolean>;
	push_public_key?: string;
}

export interface Booking {
	id: number;
	kind: 'stay' | 'logistics';
	title: string;
	note: string | null;
	start_date: string;
	end_date: string;
	user: Person;
	overlaps: number[];
}

export interface ShoppingItem {
	id: number;
	text: string;
	qty: string | null;
	store: string | null;
	added_by: Person | null;
	added_at: string;
	acquired_by: Person | null;
	acquired_at: string | null;
}

export interface Task {
	id: number;
	list_id: number;
	title: string;
	notes: string | null;
	priority: number;
	due_date: string | null;
	assignee: Person | null;
	created_by: Person | null;
	created_at: string;
	done_by: Person | null;
	done_at: string | null;
}

export interface TaskList {
	id: number;
	name: string;
	tasks: Task[];
}

export interface CameraInfo {
	id: number;
	name: string;
	model: string | null;
	online: boolean;
	last_ok_at: string | null;
	error: string | null;
	streams: Partial<Record<'sub' | 'main' | 'tele', string>>;
	ptz: boolean;
	zoom: boolean;
	presets: { id: string; name: string }[];
	auto_track: boolean | null;
	recordings: boolean;
	events: boolean;
	siren: boolean;
	light: boolean;
	ai_types: string[];
	last_event: { type: string; at: string } | null;
}
