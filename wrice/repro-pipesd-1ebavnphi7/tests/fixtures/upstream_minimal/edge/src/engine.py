from .merge import dynamic_token_scheduling_dp


class Decoding:
    def __init__(self, args):
        self.args = args
        self.merge_policy = "dp"
        self.verify_thresh_single = args.verify_thresh_single
        self.verify_thresh_multi = args.verify_thresh_multi

    def _resolve_merge_plan(self):
        batches, _ = dynamic_token_scheduling_dp([self.args.default_token_compute], 0.1, 0.2)
        return [len(batch) for batch in batches if batch]

    def if_verify(self, probs_draft, verify_mode):
        if verify_mode == 'hybrid':
            row_maxes = [max(x) for x in probs_draft]
            product = 1
            for value in row_maxes:
                product *= value
            single_flag = row_maxes[-1] < self.verify_thresh_single
            multi_flag = product < self.verify_thresh_multi
            return (single_flag or multi_flag)
        return False
