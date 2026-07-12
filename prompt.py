class AsterPrompt:
    _insturction: str

    def __init__(self, instruction:str)->None:
        self._insturction = instruction
        
    def render(self, slots:dict[str, object])->str:
        slots_formatted = "\n".join([f"{key}: {value}" for key, value in slots.items()])
        return f"{self._insturction}\n{slots_formatted}"