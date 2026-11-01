// One short message at a time, bottom of the screen.
class Toasts {
	message = $state<string | null>(null);
	kind = $state<'info' | 'error'>('info');
	/** Sheets open right now. A sheet is a modal dialog that covers the page, so while one
	 * is open the message shows inside it instead. */
	sheets = $state(0);
	#timer: ReturnType<typeof setTimeout> | undefined;

	/** A button on the message, like Undo. */
	action = $state<{ label: string; run: () => void } | null>(null);

	show(message: string, kind: 'info' | 'error' = 'info', action: { label: string; run: () => void } | null = null) {
		this.message = message;
		this.kind = kind;
		this.action = action;
		clearTimeout(this.#timer);
		this.#timer = setTimeout(() => this.dismiss(), kind === 'error' || action ? 6000 : 3000);
	}

	dismiss() {
		clearTimeout(this.#timer);
		this.message = null;
		this.action = null;
	}

	error(e: unknown) {
		this.show(e instanceof Error ? e.message : 'Something went wrong.', 'error');
	}
}

export const toast = new Toasts();
