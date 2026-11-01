// One short message at a time, bottom of the screen.
class Toasts {
	message = $state<string | null>(null);
	kind = $state<'info' | 'error'>('info');
	/** Sheets open right now. A sheet is a modal dialog that covers the page, so while one
	 * is open the message shows inside it instead. */
	sheets = $state(0);
	#timer: ReturnType<typeof setTimeout> | undefined;

	show(message: string, kind: 'info' | 'error' = 'info') {
		this.message = message;
		this.kind = kind;
		clearTimeout(this.#timer);
		this.#timer = setTimeout(() => (this.message = null), kind === 'error' ? 6000 : 3000);
	}

	error(e: unknown) {
		this.show(e instanceof Error ? e.message : 'Something went wrong.', 'error');
	}
}

export const toast = new Toasts();
